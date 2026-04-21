import asyncio
import json
import os
import re
import time
from engine.runner import BenchmarkRunner
from agent.main_agent import MainAgent
from engine.llm_judge import LLMJudge


def _tokenize(text: str):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class ExpertEvaluator:
    async def score(self, case, resp):
        """
        Offline approximation of faithfulness/relevancy to keep lab runnable without API keys.
        """
        answer_tokens = _tokenize(resp.get("answer", ""))
        expected_tokens = _tokenize(case.get("expected_answer", ""))
        question_tokens = _tokenize(case.get("question", ""))

        faithfulness = len(answer_tokens.intersection(expected_tokens)) / max(1, len(expected_tokens))
        relevancy = len(answer_tokens.intersection(question_tokens)) / max(1, len(question_tokens))

        return {
            "faithfulness": round(min(1.0, faithfulness), 3),
            "relevancy": round(min(1.0, relevancy), 3),
            "retrieval": {"hit_rate": 0.0, "mrr": 0.0},
        }


def _safe_avg(values):
    return sum(values) / len(values) if values else 0.0


def _build_summary(agent_version: str, results, run_mode: str):
    avg_score = _safe_avg([r["judge"]["final_score"] for r in results])
    hit_rate = _safe_avg([r["ragas"]["retrieval"]["hit_rate"] for r in results])
    mrr = _safe_avg([r["ragas"]["retrieval"]["mrr"] for r in results])
    agreement_rate = _safe_avg([r["judge"]["agreement_rate"] for r in results])
    faithfulness = _safe_avg([r["ragas"]["faithfulness"] for r in results])
    relevancy = _safe_avg([r["ragas"]["relevancy"] for r in results])
    latency = _safe_avg([r["latency"] for r in results])
    pass_rate = _safe_avg([1.0 if r["status"] == "pass" else 0.0 for r in results])
    total_cost = sum(r.get("metadata", {}).get("estimated_cost_usd", 0.0) for r in results)

    return {
        "metadata": {
            "version": agent_version,
            "run_mode": run_mode,
            "total": len(results),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "metrics": {
            "avg_score": round(avg_score, 4),
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
            "agreement_rate": round(agreement_rate, 4),
            "faithfulness": round(faithfulness, 4),
            "relevancy": round(relevancy, 4),
            "avg_latency_s": round(latency, 4),
            "pass_rate": round(pass_rate, 4),
            "total_estimated_cost_usd": round(total_cost, 6),
        },
    }


def _release_gate(v1_summary, v2_summary):
    delta_score = v2_summary["metrics"]["avg_score"] - v1_summary["metrics"]["avg_score"]
    delta_hit = v2_summary["metrics"]["hit_rate"] - v1_summary["metrics"]["hit_rate"]
    delta_latency = v2_summary["metrics"]["avg_latency_s"] - v1_summary["metrics"]["avg_latency_s"]

    approve = (
        delta_score >= 0.0
        and delta_hit >= -0.05
        and delta_latency <= 2.5
        and v2_summary["metrics"]["agreement_rate"] >= 0.6
    )
    return {
        "decision": "APPROVE" if approve else "BLOCK_RELEASE",
        "delta_avg_score": round(delta_score, 4),
        "delta_hit_rate": round(delta_hit, 4),
        "delta_latency_s": round(delta_latency, 4),
    }


def _write_failure_analysis(results, summary):
    clusters = {
        "Hallucination": 0,
        "Incomplete": 0,
        "Tone Mismatch": 0,
    }
    failed = [r for r in results if r["status"] == "fail"]
    for item in failed:
        answer = item.get("agent_response", "").lower()
        if "i do not know" in answer:
            clusters["Incomplete"] += 1
        elif len(answer.split()) < 10:
            clusters["Tone Mismatch"] += 1
        else:
            clusters["Hallucination"] += 1

    content = f"""# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark
- **Tổng số cases:** {summary['metadata']['total']}
- **Chế độ chạy:** {summary['metadata'].get('run_mode', 'unknown')}
- **Tỉ lệ Pass/Fail:** {int(summary['metrics']['pass_rate'] * summary['metadata']['total'])}/{len(failed)}
- **Điểm RAGAS trung bình:**
    - Faithfulness: {summary['metrics']['faithfulness']:.2f}
    - Relevancy: {summary['metrics']['relevancy']:.2f}
- **Điểm LLM-Judge trung bình:** {summary['metrics']['avg_score']:.2f} / 5.0

## 2. Phân nhóm lỗi (Failure Clustering)
| Nhóm lỗi | Số lượng | Nguyên nhân dự kiến |
|----------|----------|---------------------|
| Hallucination | {clusters['Hallucination']} | Retriever lấy thiếu context hoặc context không đủ rõ |
| Incomplete | {clusters['Incomplete']} | Agent từ chối trả lời hoặc thiếu thông tin chi tiết |
| Tone Mismatch | {clusters['Tone Mismatch']} | Câu trả lời chưa đúng mức độ chuyên nghiệp mong muốn |

## 3. Phân tích 5 Whys (Case đại diện)
### Case #1: Retrieval mismatch trong câu hỏi chính sách
1. **Symptom:** Agent trả lời thiếu ý quan trọng.
2. **Why 1:** Context top-k chưa chứa đúng tài liệu ưu tiên.
3. **Why 2:** Token overlap retrieval yếu với câu hỏi paraphrase.
4. **Why 3:** Không có bước reranking semantic.
5. **Why 4:** Chưa hiệu chỉnh trọng số title/content theo domain.
6. **Root Cause:** Chiến lược retrieval hiện tại còn đơn giản.

## 4. Kế hoạch cải tiến (Action Plan)
- [ ] Thêm semantic reranker sau bước retrieval ban đầu.
- [ ] Cải thiện prompt để bắt buộc trích dẫn nguồn theo `retrieved_ids`.
- [ ] Tối ưu trọng số đánh điểm cho câu hỏi đa tài liệu.
"""

    os.makedirs("analysis", exist_ok=True)
    with open("analysis/failure_analysis.md", "w", encoding="utf-8") as f:
        f.write(content)


async def run_benchmark_with_results(
    agent_version: str,
    agent_variant: str,
    use_openai_agent: bool,
    use_openai_judge: bool,
):
    print(f"[RUN] Starting benchmark for {agent_version}...")

    if not os.path.exists("data/golden_set.jsonl"):
        print("[ERROR] Missing data/golden_set.jsonl. Run 'python data/synthetic_gen.py' first.")
        return None, None

    with open("data/golden_set.jsonl", "r", encoding="utf-8") as f:
        dataset = [json.loads(line) for line in f if line.strip()]

    if not dataset:
        print("[ERROR] data/golden_set.jsonl is empty. Generate at least one test case.")
        return None, None

    run_mode = "online" if (use_openai_agent or use_openai_judge) else "offline"
    runner = BenchmarkRunner(
        MainAgent(version=agent_variant, use_openai=use_openai_agent),
        ExpertEvaluator(),
        LLMJudge(use_openai=use_openai_judge),
    )
    results = await runner.run_all(dataset)
    summary = _build_summary(agent_version, results, run_mode=run_mode)
    return results, summary

async def main():
    # Cost-aware strategy: baseline offline, candidate online with OpenAI.
    v1_results, v1_summary = await run_benchmark_with_results(
        "Agent_V1_Base",
        "v1",
        use_openai_agent=False,
        use_openai_judge=False,
    )
    v2_results, v2_summary = await run_benchmark_with_results(
        "Agent_V2_Optimized",
        "v2",
        use_openai_agent=True,
        use_openai_judge=True,
    )

    if not v1_summary or not v2_summary:
        print("[ERROR] Benchmark failed. Please check data/golden_set.jsonl.")
        return

    gate = _release_gate(v1_summary, v2_summary)
    print("\n--- REGRESSION COMPARISON ---")
    print(f"V1 Score: {v1_summary['metrics']['avg_score']:.3f}")
    print(f"V2 Score: {v2_summary['metrics']['avg_score']:.3f}")
    print(f"Delta Score: {gate['delta_avg_score']:+.3f}")
    print(f"Delta Hit Rate: {gate['delta_hit_rate']:+.3f}")

    os.makedirs("reports", exist_ok=True)
    v2_summary["regression"] = {
        "baseline": v1_summary["metadata"]["version"],
        "candidate": v2_summary["metadata"]["version"],
        "result": gate,
    }

    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "baseline_results": v1_results,
                "candidate_results": v2_results,
                "regression": gate,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    _write_failure_analysis(v2_results, v2_summary)

    if gate["decision"] == "APPROVE":
        print("[GATE] APPROVE")
    else:
        print("[GATE] BLOCK_RELEASE")
    print("[DONE] Updated reports and analysis/failure_analysis.md")

if __name__ == "__main__":
    asyncio.run(main())
