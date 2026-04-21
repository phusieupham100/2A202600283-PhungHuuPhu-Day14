import re
import json
import os
from typing import Any, Dict, Set
from dotenv import load_dotenv
from openai import AsyncOpenAI


def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _to_five_point(normalized_score: float) -> float:
    return max(1.0, min(5.0, round(1.0 + normalized_score * 4.0, 2)))


class LLMJudge:
    """
    Offline multi-judge simulation.
    Judge A and Judge B use different heuristics to mimic model disagreement.
    """

    def __init__(self, use_openai: bool = True):
        load_dotenv()
        self.rubrics = {
            "accuracy": "Semantic overlap between answer and ground truth.",
            "relevance": "Answer should directly respond to question intent.",
            "safety": "Refuse clearly unsafe/out-of-scope requests.",
        }
        self.use_openai = use_openai
        self.model_a = os.getenv("OPENAI_JUDGE_MODEL_A", "gpt-4o-mini")
        self.model_b = os.getenv("OPENAI_JUDGE_MODEL_B", "gpt-4o")
        self._client = (
            AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            if (self.use_openai and os.getenv("OPENAI_API_KEY"))
            else None
        )

    def _judge_a(self, answer: str, ground_truth: str) -> float:
        a_tokens = _tokenize(answer)
        gt_tokens = _tokenize(ground_truth)
        if not gt_tokens:
            return 3.0
        overlap = len(a_tokens.intersection(gt_tokens)) / max(1, len(gt_tokens))
        return _to_five_point(overlap)

    def _judge_b(self, question: str, answer: str, ground_truth: str) -> float:
        q_tokens = _tokenize(question)
        a_tokens = _tokenize(answer)
        gt_tokens = _tokenize(ground_truth)
        relevance = len(q_tokens.intersection(a_tokens)) / max(1, len(q_tokens))
        grounded = len(a_tokens.intersection(gt_tokens)) / max(1, len(a_tokens))
        hybrid = 0.45 * relevance + 0.55 * grounded
        return _to_five_point(hybrid)

    def _resolve_conflict(self, score_a: float, score_b: float) -> float:
        if abs(score_a - score_b) <= 1.0:
            return round((score_a + score_b) / 2, 2)
        # Conflict resolution: prefer stricter score to reduce false positives.
        return round(min(score_a, score_b) + 0.25, 2)

    async def evaluate_multi_judge(
        self, question: str, answer: str, ground_truth: str
    ) -> Dict[str, Any]:
        if self._client:
            score_a = await self._judge_with_openai(
                self.model_a, "Strictly prioritize factual correctness.", question, answer, ground_truth
            )
            score_b = await self._judge_with_openai(
                self.model_b, "Prioritize user relevance and response usefulness.", question, answer, ground_truth
            )
        else:
            score_a = self._judge_a(answer, ground_truth)
            score_b = self._judge_b(question, answer, ground_truth)
        final_score = self._resolve_conflict(score_a, score_b)

        diff = abs(score_a - score_b)
        agreement_rate = round(max(0.0, 1.0 - diff / 4.0), 2)
        reasoning = (
            "Strong agreement between judges."
            if diff <= 0.5
            else "Moderate disagreement handled by conflict resolver."
        )

        return {
            "final_score": final_score,
            "agreement_rate": agreement_rate,
            "individual_scores": {"judge_a": score_a, "judge_b": score_b},
            "conflict_detected": diff > 1.0,
            "reasoning": reasoning,
            "judge_models": [self.model_a, self.model_b] if self._client else ["offline_a", "offline_b"],
        }

    async def _judge_with_openai(
        self,
        model: str,
        judge_style: str,
        question: str,
        answer: str,
        ground_truth: str,
    ) -> float:
        fallback = self._judge_b(question, answer, ground_truth)
        if not self._client:
            return fallback

        system_prompt = (
            "You are an evaluation judge. "
            f"{judge_style} "
            "Return only JSON with keys: score, rationale. "
            "score must be a number between 1 and 5."
        )
        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Ground truth:\n{ground_truth}\n\n"
            f"Agent answer:\n{answer}\n"
        )

        try:
            resp = await self._client.chat.completions.create(
                model=model,
                temperature=0.0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = self._extract_json(raw)
            score = float(parsed.get("score", fallback))
            return max(1.0, min(5.0, round(score, 2)))
        except Exception:
            # Retry once with mini model to reduce hard failures.
            if model != "gpt-4o-mini":
                try:
                    resp = await self._client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0.0,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    )
                    raw = (resp.choices[0].message.content or "").strip()
                    parsed = self._extract_json(raw)
                    score = float(parsed.get("score", fallback))
                    return max(1.0, min(5.0, round(score, 2)))
                except Exception:
                    return fallback
            return fallback

    def _extract_json(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            pass

        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
        return {}
