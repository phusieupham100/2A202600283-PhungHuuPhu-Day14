# Day 14 Solo To-Do (AI Evaluation Factory)

## 1) Goal of today
- Build a complete evaluation pipeline for an AI agent.
- Prove quality with measurable metrics (not only demos).
- Produce all required submission artifacts in the correct format.

## 2) Required deliverables
- [ ] `reports/summary.json`
- [ ] `reports/benchmark_results.json`
- [ ] `analysis/failure_analysis.md`
- [ ] `analysis/reflections/reflection_[YourName].md`
- [ ] Source code in this repo

## 3) Hard requirements from rubric
- [ ] At least **50 test cases** in `data/golden_set.jsonl`
- [ ] Retrieval metrics: **Hit Rate** and **MRR**
- [ ] Multi-judge with at least **2 judges/models**
- [ ] Agreement metric and conflict handling
- [ ] Regression comparison (old vs new version)
- [ ] Auto release gate decision (approve/block)
- [ ] Async benchmark execution

## 4) Suggested solo execution order
1. Generate dataset
   - Run: `python data/synthetic_gen.py`
   - Check: `data/golden_set.jsonl` exists and has 50+ lines

2. Run benchmark + regression
   - Run: `python main.py`
   - Check: `reports/summary.json` and `reports/benchmark_results.json`

3. Validate submission format
   - Run: `python check_lab.py`
   - Fix any missing file/field warnings

4. Complete personal reflection
   - Create: `analysis/reflections/reflection_[YourName].md`

## 5) What to verify before submission
- [ ] No API key leaked (`.env` is not committed)
- [ ] `summary.json` includes `metrics` and `metadata`
- [ ] `metrics.hit_rate` exists
- [ ] `metrics.agreement_rate` exists
- [ ] Regression information is present
- [ ] Failure analysis explains root causes and action plan

## 6) Timebox plan (4 hours)
- 45m: Dataset + hard cases
- 90m: Eval engine + async runner + judges
- 60m: Benchmark + error clustering + 5 whys
- 45m: Optimize + finalize report + run checker

## 7) Common risks and quick fixes
- If retrieval score is low:
  - Improve query-document matching
  - Tune top-k
- If judge disagreement is high:
  - Tighten rubric
  - Add conflict-resolution rule
- If runtime is slow:
  - Lower batch size only if needed for rate-limit
  - Keep async processing

## 8) Final command sequence
```bash
pip install -r requirements.txt
python data/synthetic_gen.py
python main.py
python check_lab.py
```
