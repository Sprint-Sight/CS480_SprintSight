# SprintSight model-comparison evaluation

Preliminary pipeline for comparing local Ollama models (currently
`sprintsight-qwen`, `sprintsight-mistral`, `sprintsight-gemma`) on
identical sprint inputs with full MLflow provenance.

The external quality judge is owned by a separate teammate. This pipeline
leaves a `judge_quality_score` column in every per-example row and
provides `attach_judge_scores.py` for them to populate it later. All the
other metrics here are judge-independent — the pipeline can produce
defensible preliminary results even if the judge work is not yet ready.

## Why this package is separate from `research/validation_harness.py`

`validation_harness.py` tests a different property (does the engine
produce the EXPECTED ORDERING across hand-crafted fixtures?). It is a
sanity-check harness, not a model-comparison harness. This package is the
model-comparison harness and feeds the final report.

## Layout

| File | Role |
|---|---|
| `datasets.py` | Named + hashed datasets. `d1_fixtures` wraps the existing 5-fixture set; add `d2_*`/`d3_*` by appending to `DATASETS`. |
| `runner.py` | `run_evaluation(...)` — ONE condition per MLflow run (model × dataset × prompt × seed). Judge-independent metrics computed inline. |
| `metrics.py` | Per-example scoring: format validity, groundedness, dimension completion, overall score. All without the external judge. |
| `analysis.py` | Loads per-example rows from MLflow runs, builds comparison tables, computes paired bootstrap CIs. |
| `plots.py` | Four report-ready plots (latency, format-validity, token distribution, pairwise CIs). |
| `cli.py` | `python -m research.eval.cli …` driver. |
| `attach_judge_scores.py` | Hand-off from the judging pipeline. |

## Typical invocation

```bash
# From ai-engine/ , with MLFLOW_TRACKING_URI set (defaults to http://localhost:5000).

# 1. Smoke-test on one example per model so you know the pipeline works
#    before paying full compute cost.
python -m research.eval.cli run --model sprintsight-qwen \
    --dataset d1_fixtures --subset high_performing --note "smoke test"

# 2. Full preliminary sweep: 3 models × full dataset × 1 repeat.
for M in sprintsight-qwen sprintsight-mistral sprintsight-gemma; do
    python -m research.eval.cli run \
        --model "$M" --dataset d1_fixtures \
        --prompt-version v1.0 --phase preliminary
done

# 3. Rerun with repeats=3 ONLY on the models that survived step 2, to
#    measure within-model consistency.
for M in sprintsight-qwen sprintsight-mistral sprintsight-gemma; do
    python -m research.eval.cli run \
        --model "$M" --dataset d1_fixtures --repeats 3 \
        --prompt-version v1.0 --phase deep_eval
done

# 4. Produce tables, pairwise CIs, and plots.
python -m research.eval.cli analyze \
    --experiment sprintsight-model-comparison \
    --out-dir research/eval_report \
    --pairwise-metric overall_score
```

Once the judge pipeline emits a CSV:

```bash
python -m research.eval.attach_judge_scores \
    --judge-file path/to/judge_scores.csv \
    --run-id <mlflow run id of the sweep run>

# Then redo the analysis with the judge-rated metric as the headline.
python -m research.eval.cli analyze \
    --experiment sprintsight-model-comparison \
    --out-dir research/eval_report_with_judge \
    --pairwise-metric judge_quality_score
```

## MLflow data layout

- **Experiment:** one per research question. `sprintsight-model-comparison`
  for this phase; `sprintsight-prompt-ablation` later if you test prompt
  variants; `sprintsight-finetune-eval` only if fine-tuning happens.
- **Run:** one per `(model × dataset × prompt_version × seed)`. We do NOT
  nest a child MLflow run per example — the UI becomes unusable with
  hundreds of nested runs. Per-example data lives in the `per_example.jsonl`
  artifact and the `per_example_table.json` table instead.
- **Params:** every reproducibility knob (model_name, model_digest,
  ollama_version, dataset_hash, prompt_hash, git_sha, python_version,
  seed, repeats, phase). Params are immutable per run.
- **Metrics:** run-level aggregates only (`format_validity_rate`,
  `latency_mean_s`, `latency_p95_s`, `groundedness_rate_mean`,
  `overall_score_mean`, `dimension_completion_rate_mean`,
  `error_rate`, `n_examples`). Per-example numbers stay in the artifact.
- **Tags:** filters you'll actually use (`model`, `dataset`,
  `prompt_version`, `phase`, `run_type`).
- **Artifacts:** `per_example.jsonl` (long-term store), `per_example_table.json`
  (sortable in UI), `raw_outputs/raw__<example>__r<n>.json` (full
  SprintAssessment per example).

## How to prevent mixing preliminary and final results

Use the `phase` tag. Default is `preliminary`. When Dataset 2 and 3 land
and you redo the sweep, pass `--phase deep_eval` or `--phase final`. The
analysis layer accepts a `--filter` string, so a report-worthy run uses
`--filter 'tags.phase = "final"'`.

Experiment names, dataset names, and phases together give you three
independent axes to carve by — in practice `phase` is the one you'll use
most.
