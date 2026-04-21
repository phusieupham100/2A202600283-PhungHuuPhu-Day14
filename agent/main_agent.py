import asyncio
import json
import os
import re
from typing import Dict, List, Set
from dotenv import load_dotenv
from openai import AsyncOpenAI


def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class MainAgent:
    """
    Lightweight RAG-style agent for offline lab benchmarking.
    version="v2" applies a slightly stricter answer policy.
    """

    def __init__(self, version: str = "v1", use_openai: bool = True):
        load_dotenv()
        self.version = version
        self.name = f"SupportAgent-{version}"
        self.corpus = self._load_corpus()
        self.use_openai = use_openai
        self.openai_model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
        self._client = (
            AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            if (self.use_openai and os.getenv("OPENAI_API_KEY"))
            else None
        )

    def _load_corpus(self) -> List[Dict]:
        path = "data/corpus.json"
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _retrieve(self, question: str, top_k: int = 3) -> List[Dict]:
        q_tokens = _tokenize(question)
        expanded_tokens = set(q_tokens)
        synonym_map = {
            "refund": {"billing", "refundable"},
            "rollback": {"incident", "error", "release"},
            "password": {"security", "authentication"},
            "latency": {"performance", "slow"},
            "rate": {"limit", "threshold"},
            "policy": {"rule", "guideline"},
        }
        for token in list(q_tokens):
            expanded_tokens.update(synonym_map.get(token, set()))

        scored = []
        for doc in self.corpus:
            title_tokens = _tokenize(doc["title"])
            content_tokens = _tokenize(doc["content"])
            title_overlap = len(expanded_tokens.intersection(title_tokens))
            content_overlap = len(expanded_tokens.intersection(content_tokens))
            # Weighted title match helps policy-name queries map to the right document.
            weighted_score = (2.0 * title_overlap) + content_overlap
            scored.append((weighted_score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored[:top_k] if score > 0]

    async def query(self, question: str) -> Dict:
        await asyncio.sleep(0.05)
        retrieved_docs = self._retrieve(question, top_k=3)

        answer, usage = await self._generate_answer(question, retrieved_docs)
        estimated_tokens = usage if usage is not None else max(40, len(answer.split()) * 2 + len(question.split()))
        contexts = [d["content"] for d in retrieved_docs]
        retrieved_ids = [d["id"] for d in retrieved_docs]

        return {
            "answer": answer,
            "contexts": contexts,
            "retrieved_ids": retrieved_ids,
            "metadata": {
                "model": self.openai_model if usage is not None else "local-heuristic-rag",
                "mode": "openai" if usage is not None else "offline",
                "tokens_used": estimated_tokens,
                "estimated_cost_usd": round(estimated_tokens * 0.000002, 6),
            },
        }

    async def _generate_answer(self, question: str, retrieved_docs: List[Dict]):
        if not retrieved_docs:
            return "I do not know based on the available documentation.", None

        snippets = [f"{d['title']}: {d['content']}" for d in retrieved_docs[:2]]
        heuristic_answer = " ".join(snippets)
        if self.version == "v2":
            heuristic_answer = heuristic_answer[:360]

        if not self._client:
            return heuristic_answer, None

        context_block = "\n".join(f"- {s}" for s in snippets)
        system_prompt = (
            "You are a reliable support assistant. "
            "Answer only from provided context. "
            "If context is insufficient, say you do not know."
        )
        user_prompt = (
            f"Question:\n{question}\n\n"
            f"Context:\n{context_block}\n\n"
            "Return a concise, factual answer."
        )

        try:
            resp = await self._client.chat.completions.create(
                model=self.openai_model,
                temperature=0.1 if self.version == "v2" else 0.3,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            answer = (resp.choices[0].message.content or "").strip() or heuristic_answer
            usage = resp.usage.total_tokens if resp.usage else None
            return answer, usage
        except Exception:
            # Keep pipeline resilient if API quota/model errors happen.
            return heuristic_answer, None


if __name__ == "__main__":
    agent = MainAgent(version="v2")

    async def test():
        resp = await agent.query("When should we roll back a deployment?")
        print(resp)

    asyncio.run(test())
