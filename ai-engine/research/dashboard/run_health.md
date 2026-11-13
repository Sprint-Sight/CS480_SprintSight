# Run health: local-LLM grading batch

Generated 2026-11-12T11:30:20 by `research/dashboard/analyze.py` (read-only on `results/` and `audit_logs/`).

Batch = files in `ai-engine/results/` modified in the last 48 h: **30 files**. Older files excluded: 0.

Each invocation writes 3 files sharing one session timestamp (`services/save_results.py`: `_SESSION_TS` is set once per process): `raw_results_<experiment>_<ts>.jsonl`, `summary_<experiment>_<ts>.json` and `raw_judge_results_<experiment>_<ts>.jsonl`. Nothing is overwritten on re-run unless two processes start in the same second.

| Script | Model | Session | Files | Runs (expected / raw lines / summary) | Repeats per bundle | Dims scored | Complete runs | Judge rows | Median s | Verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cs203 | qwen25-32b | 20261111T123146 | 3/3 | 6 / 6 / 6 | CS203 G6 3, CS203 JY 3 | 36/36 | 6/6 | 6 | 49.5 | **OK** | all runs, dimensions, summary and judge rows as expected |
| cs203 | qwen | 20261111T125443 | 3/3 | 6 / 6 / 6 | CS203 G6 3, CS203 JY 3 | 36/36 | 6/6 | 6 | 84.7 | **OK** | all runs, dimensions, summary and judge rows as expected |
| cs203 | gemma | 20261111T132459 | 3/3 | 6 / 6 / 6 | CS203 G6 3, CS203 JY 3 | 29/36 | 2/6 | 6 | 348.6 | **PARTIAL** | 7 failed dimensions: 7× output truncated (max_tokens) |
| cs203 | r1-32b | 20261111T141745 | 3/3 | 6 / 6 / 6 | CS203 G6 3, CS203 JY 3 | 35/36 | 5/6 | 6 | 156.9 | **PARTIAL** | 1 failed dimensions: 1× schema: justification over 500 chars |
| cs203 | coder-32b | 20261111T145131 | 3/3 | 6 / 6 / 6 | CS203 G6 3, CS203 JY 3 | 36/36 | 6/6 | 6 | 58.9 | **OK** | all runs, dimensions, summary and judge rows as expected |
| fixture | qwen25-32b | 20261111T073959 | 3/3 | 15 / 15 / 15 | Alpha 3, Delta 3, Epsilon 3, Theta 3, Gamma 3 | 90/90 | 15/15 | 15 | 48.0 | **OK** | all runs, dimensions, summary and judge rows as expected |
| fixture | qwen | 20261111T080921 | 3/3 | 15 / 15 / 15 | Alpha 3, Delta 3, Epsilon 3, Theta 3, Gamma 3 | 87/90 | 12/15 | 15 | 100.8 | **PARTIAL** | 3 failed dimensions: 3× output truncated (max_tokens) |
| fixture | gemma | 20261111T085747 | 3/3 | 15 / 15 / 15 | Alpha 3, Delta 3, Epsilon 3, Theta 3, Gamma 3 | 76/90 | 4/15 | 15 | 191.7 | **PARTIAL** | 14 failed dimensions: 14× output truncated (max_tokens) |
| fixture | r1-32b | 20261111T100912 | 3/3 | 15 / 15 / 15 | Alpha 3, Delta 3, Epsilon 3, Theta 3, Gamma 3 | 88/90 | 13/15 | 15 | 150.9 | **PARTIAL** | 2 failed dimensions: 2× schema: justification over 500 chars |
| fixture | coder-32b | 20261111T110105 | 3/3 | 15 / 15 / 15 | Alpha 3, Delta 3, Epsilon 3, Theta 3, Gamma 3 | 90/90 | 15/15 | 15 | 49.4 | **OK** | all runs, dimensions, summary and judge rows as expected |

## Failed dimensions

| Script | Model | Bundle | Repeat | Dimension | Class | Run seconds | Audit attempts |
|---|---|---|---|---|---|---|---|
| cs203 | gemma | CS203 G6 | 1 | documentation | output truncated (max_tokens) | 421.06 | 3 |
| cs203 | gemma | CS203 G6 | 1 | collaboration | output truncated (max_tokens) | 421.06 | 3 |
| cs203 | gemma | CS203 JY | 1 | testing | output truncated (max_tokens) | 464.12 | 3 |
| cs203 | gemma | CS203 JY | 1 | documentation | output truncated (max_tokens) | 464.12 | 3 |
| cs203 | gemma | CS203 JY | 1 | collaboration | output truncated (max_tokens) | 464.12 | 3 |
| cs203 | gemma | CS203 JY | 2 | collaboration | output truncated (max_tokens) | 403.27 | 3 |
| cs203 | gemma | CS203 JY | 3 | collaboration | output truncated (max_tokens) | 238.96 | 3 |
| cs203 | r1-32b | CS203 G6 | 1 | code_quality | schema: justification over 500 chars | 215.34 | 5 |
| fixture | qwen | Alpha | 1 | testing | output truncated (max_tokens) | 228.52 | 3 |
| fixture | qwen | Alpha | 2 | testing | output truncated (max_tokens) | 307.11 | 3 |
| fixture | qwen | Alpha | 3 | testing | output truncated (max_tokens) | 225.82 | 3 |
| fixture | gemma | Alpha | 1 | collaboration | output truncated (max_tokens) | 242.04 | 3 |
| fixture | gemma | Alpha | 2 | collaboration | output truncated (max_tokens) | 209.33 | 3 |
| fixture | gemma | Alpha | 3 | collaboration | output truncated (max_tokens) | 184.36 | 3 |
| fixture | gemma | Delta | 2 | collaboration | output truncated (max_tokens) | 186.3 | 3 |
| fixture | gemma | Epsilon | 1 | collaboration | output truncated (max_tokens) | 311.75 | 3 |
| fixture | gemma | Epsilon | 2 | testing | output truncated (max_tokens) | 401.5 | 3 |
| fixture | gemma | Epsilon | 2 | documentation | output truncated (max_tokens) | 401.5 | 3 |
| fixture | gemma | Epsilon | 2 | collaboration | output truncated (max_tokens) | 401.5 | 3 |
| fixture | gemma | Epsilon | 3 | collaboration | output truncated (max_tokens) | 174.13 | 3 |
| fixture | gemma | Gamma | 1 | collaboration | output truncated (max_tokens) | 191.71 | 3 |
| fixture | gemma | Gamma | 2 | collaboration | output truncated (max_tokens) | 276.2 | 3 |
| fixture | gemma | Theta | 1 | collaboration | output truncated (max_tokens) | 183.48 | 3 |
| fixture | gemma | Theta | 2 | testing | output truncated (max_tokens) | 267.1 | 3 |
| fixture | gemma | Theta | 2 | collaboration | output truncated (max_tokens) | 267.1 | 3 |
| fixture | r1-32b | Epsilon | 2 | code_quality | schema: justification over 500 chars | 216.29 | 5 |
| fixture | r1-32b | Epsilon | 3 | code_quality | schema: justification over 500 chars | 212.57 | 5 |

## Checks

- Summary files agree with raw files for every invocation: yes.
- Scores in audit logs match raw scores on 603 linked dimensions; mismatches: 0.
- `<think>` tags in raw model output: 0. Calls at the num_ctx ceiling: 0; largest prompt = 55% of num_ctx.
- Calls that trip the 'prompt most likely truncated' warning (reported < 75% of estimate): 148 of 838; median reported/estimate = 0.796. None is near the context limit, so these warnings are false positives from the chars/4 estimate.
- Instant failures (< 2 s): 0. Retry spirals (> 3x model median): 1.
- Judge calls in the batch window: {'judge-phi': 140, 'gpt-4o-mini': 177}. Fixture traces are judged by gpt-4o-mini through OpenAI (`judges/citation_ground_custom_judge.py:199-201`), although the judge files label every row `sprintsight-judge-phi`.
- Activity after the batch: 36 calls {'qwen25-32b | Connection error.': 36} between 2026-11-11 15:28:48.204916+00:00 and 2026-11-11 15:29:28.009972+00:00 UTC, with no result files.
- Expected-order links the team-authored gold itself violates: collaboration|lone_contributor_poor_outcome > struggling.
