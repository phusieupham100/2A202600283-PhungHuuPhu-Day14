# Day 14 Submission Summary

## Scope delivered
- Golden dataset generation with 50 test cases.
- Retrieval evaluation with Hit Rate and MRR.
- Multi-judge consensus scoring with agreement and conflict handling.
- Regression benchmarking and release gate decision.
- Failure analysis and personal reflection documentation.

## Run commands
```bash
python data/synthetic_gen.py
python main.py
python check_lab.py
```

## Final metrics (latest run)
- Version: `Agent_V2_Optimized`
- Run mode: `online`
- Avg score: `4.91`
- Hit rate: `0.96`
- MRR: `0.95`
- Agreement rate: `0.955`
- Avg latency (s): `1.2238`
- Estimated total eval cost (USD): `0.014448`
- Regression decision: `APPROVE`

## Required files checklist
- [x] `reports/summary.json`
- [x] `reports/benchmark_results.json`
- [x] `analysis/failure_analysis.md`
- [x] `analysis/reflections/reflection_YourName.md`

## Notes
- The project supports fallback offline mode when OpenAI API is unavailable.
- Do not commit `.env` with real API keys.
