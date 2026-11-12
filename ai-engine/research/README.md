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
docker compose exec sprintsight_ai python -m research.trials.run_fixture_trial --model sprintsight-qwen
python -m research.trials.validation_harness --help
```

`research/eval_report/`, `research/eval_inspection/` and `research/judge_eval_report/` are where
the `evaluation/offline` CLIs write by default; like `research/validation_results/`, they are
outputs, not code.
