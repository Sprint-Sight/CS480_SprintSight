# research/: experiment scratchpad

One-off experiment drivers and the scripts that produce the GPU evidence for the report.
Nothing in the engine imports from here: reusable evaluation code (judges, benchmarks, the
model-comparison pipeline, the judge study and canary) lives in `evaluation/`.

Run everything from `ai-engine/` with the venv active (or inside the container with
`docker compose exec sprintsight_ai ...`). All default input and output paths are relative to
`ai-engine/`.

| Script | What it does | Reads | Writes |
|---|---|---|---|
| `compare_runs.py` | Checks that a performance change did not change grading output: compares assessment runs of the same sprint dimension by dimension. Exits 1 if any score differs. | `audit_logs/request_markers.jsonl`, `audit_logs/llm_*.txt` | stdout |
| `gpu/bench.py` | Replays recorded grading prompts against Ollama's native API at several concurrency levels to measure prefill/decode throughput. | `audit_logs/llm_*.txt` | `gpu_logs/bench_*.jsonl` |
| `gpu/report.py` | Joins the Slurm job's nvidia-smi CSV with request markers: GPU utilisation while busy, idle gaps, VRAM, power, throughput. `--mlflow` logs it to `llmops.experiments.GPU_UTILISATION`. | `gpu_logs/<job>.gpu.csv`, request markers | `gpu_logs/report_<timestamp>/` |
| `gpu/figures.py` | Report figures: `before-after` (two GPU timelines) and `models` (one row per model). PNG at 200 dpi plus vector PDF. | the same inputs as `gpu/report.py` | `gpu_logs/figures/gpu_before_after.*`, `gpu_logs/figures/gpu_per_model.*` |
| `trials/run_fixture_trial.py` | One register, grade, judge and promote cycle per model on the five synthetic_v2 teams, through the same code path as the API. | `evaluation/benchmarks/synthetic_v2.py` | MLflow (`--experiment-name`) |
| `trials/run_cs203_trial.py` | The same cycle on the two real CS203 sprints. | `evaluation/benchmarks/cs203.py` | MLflow (`--experiment-name`) |
| `trials/validation_harness.py` | Grading checks that need no gold: structural validity, the expected ordering of the synthetic_v1 teams, repeat variance and cross-model agreement. | `evaluation/benchmarks/synthetic_v1.py`, `expected_orders.py` | `research/validation_results/`, MLflow (`VALIDATION_HARNESS`) |

The step-by-step commands for the HPC GPU runs are in `hpc/README.md`; those for the model
comparison and the judge study are in `evaluation/offline/RUNBOOK.md`.

```bash
python -m research.compare_runs --list
python -m research.gpu.bench --model sprintsight-llama31 --concurrency 1,2,4
python -m research.gpu.report --gpu-csv gpu_logs/<jobid>.gpu.csv --markers audit_logs/request_markers.jsonl --mlflow
python -m research.gpu.figures before-after --help
```

`research/eval_report/`, `research/eval_inspection/` and `research/judge_eval_report/` are where
the `evaluation/offline` CLIs write by default; like `research/validation_results/`, they are
outputs, not code.

## Running the grading trials (5 models x 3 repeats)

Run from `ai-engine/`. Each invocation grades every bundle
`--repeats` times with one model, judges each run, and writes three files to `results/`
(`raw_results_*.jsonl`, `summary_*.json`, `raw_judge_results_*.jsonl`) that share one timestamp.
Give each batch its own `--experiment-name`, so the judge only sees that batch's traces.

**Fixture teams** (5 synthetic teams x 3 repeats = 15 runs per model):

```bash
for m in sprintsight-qwen25-32b sprintsight-qwen sprintsight-gemma sprintsight-r1-32b sprintsight-coder-32b; do
  docker compose exec sprintsight_ai python -m research.trials.run_fixture_trial \
    --model "$m" --repeats 3 --experiment-name "fixtures-trial-<date>"
done
```

**CS203 bundles** (2 real sprints x 3 repeats = 6 runs per model):

```bash
for m in sprintsight-qwen25-32b sprintsight-qwen sprintsight-gemma sprintsight-r1-32b sprintsight-coder-32b; do
  docker compose exec sprintsight_ai python -m research.trials.run_cs203_trial \
    --model "$m" --repeats 3 --experiment-name "cs203-trial-<date>"
done
```

Together that is 10 invocations, 105 runs and 30 result files.

Fixture traces are tagged `fixture=true` and judged by `gpt-4o-mini` through the OpenAI API
(`judges/citation_ground_custom_judge.py`), so they need `OPENAI_API_KEY`. The CS203 runs use the
local `sprintsight-judge-phi` model, so no real student data leaves the machine.

### Why 3 repeats

One run per bundle cannot separate a model's real behaviour from run-to-run noise. Three repeats give:

- **A noise estimate.** The standard deviation across repeats is how stability is reported. In the
  11 Nov batch only 42% to 92% of (bundle, dimension) scores were identical across repeats,
  depending on the model, even though the requests use temperature 0.
- **A fair ordering check.** `check_order` in `evaluation/benchmarks/expected_orders.py` only passes a
  ">" link when the gap between two fixtures is larger than their combined standard deviation.
  With one repeat that deviation is 0 and every small gap counts as a real difference.
- **A minimum sample size.** Two repeats give a very rough standard deviation, and more than three
  multiplies GPU time (the 32B models take 50 to 300 s per run).

Three is a pilot-sized compromise. It is still too few for significance claims.

## Running the dashboard

Two dashboards read the same result files. The data they need:

| Data | Where | Needed by |
|---|---|---|
| `raw_results_*.jsonl`, `summary_*.json`, `raw_judge_results_*.jsonl` (3 files per invocation, same timestamp) | `results/` | both |
| `audit_logs/llm_*.txt` (failure causes and citation checks; large and gitignored) | `audit_logs/` | static dashboard only |
| Reference scores: `evaluation/benchmarks/data/gold/*_GOLD.json`, `evaluation/benchmarks/cs203.py` and `expected_orders.py` | in the repo | static dashboard only |

**Static HTML dashboard** (run health, scorecard, heatmaps, fixture ordering, latency, grounding, run explorer):

```bash
python3 research/dashboard/analyze.py          # writes analysis.json, results_tidy.csv, run_health.md
python3 research/dashboard/build_dashboard.py  # writes dashboard.html (self-contained)
open research/dashboard/dashboard.html
```

`analyze.py` reads every file in `results/`. Narrow it with `--since 2026-11-11` (session date) or
`--experiment fixtures-trial` (text in the file name). Because it pools sessions of the same model and
script, use a filter when `results/` mixes experiments with different prompts or judges. It uses only the
Python standard library. Sessions with only a judge file (no `raw_results_*`) are skipped.

**Streamlit dashboard** (accuracy against the reference, interactive filters):

```bash
pip install streamlit pandas "altair>=5"
streamlit run research/dashboard/dashboard.py
```

It reads `results/` by default; change the folder in the sidebar if needed. It does not need the audit logs.
