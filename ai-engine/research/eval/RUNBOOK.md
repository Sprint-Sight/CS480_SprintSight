# SprintSight evaluation & research runbook

Every command needed to produce the evaluation results, in order. Run all of
these from `ai-engine/` with the venv active.

```bash
cd ai-engine
.venv/Scripts/activate        # Windows
# source .venv/bin/activate   # Linux/macOS
```

---

## 0. Environment variables that actually matter

| Variable | Why | Value |
|---|---|---|
| `OLLAMA_BASE_URL` | **The #1 gotcha.** `.env` holds the value the *Docker container* uses (`http://host.docker.internal:11435/v1`). The research CLIs run on the **host**, where that name does not resolve. | host + HPC tunnel: `http://localhost:11435/v1`<br>host + local Ollama: `http://localhost:11434/v1` |
| `MLFLOW_TRACKING_URI` | Defaults to `http://localhost:5000` (`llmops/mlflow_config.py`). MLflow 3.16 **refuses** a bare `./mlruns` file store. | `http://localhost:5000` (server), or `sqlite:///mlflow.db` offline |
| `SPRINTSIGHT_JUDGE_MODEL` | Judge tag. Must not be a llama derivative — see §2. | `phi4:14b` |
| `SPRINTSIGHT_JUDGE_BUNDLE_CHARS` | Budget for the evidence view (default 32000). The judge is shown the *candidate's* sampled commits, not the raw bundle, so this rarely bites. Do **not** raise it to "fix" truncation — the full real-sprint bundle renders at up to 2.4 MB. | leave |
| `SPRINTSIGHT_JUDGE_NUM_CTX` | **Required, and easy to miss.** Sent as Ollama `options.num_ctx`. Ollama applies a small default and truncates an over-long prompt *silently*, which would defeat every budget above. Must not exceed the judge's real ceiling. | `16384` for phi4:14b<br>`32768` for qwen2.5:14b-instruct<br>`0` to let Ollama decide |
| `SPRINTSIGHT_JUDGE_SEED` | Judge determinism (default 7). | leave |
| `SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE` | Bypasses the self-preference guard. Only to *measure* the bias. | unset |
| `LLM_TEMPERATURE` | All grading + judging calls (default 0). | leave at 0 |
| `EVAL_REAL_SPRINTS_DIR` | Where `d_real_sprints` reads from. | default is fine |

---

## 1. Infrastructure — pick one path

### Path A — HPC GPU (required for real runs)

Three terminals.

**Terminal 1 — submit the GPU job (on the cluster):**
```bash
ssh <netid>@origami.smu.edu.sg
mkdir -p ~/slurm-logs
cd ~/CS480_SprintSight/ai-engine/hpc
bash setup_ollama_container.sh      # one time only
sbatch ollama_gpu.sbatch
squeue --me                          # note the compute node hostname
```

**Terminal 2 — open the tunnel (blocking, leave it running):**
```bash
make hpc-tunnel
```

**Terminal 3 — bring up the rest of the stack:**
```bash
make hpc
make hpc-status      # verifies job + tunnel + models + Docker + /health
```

### Path B — fully local (CPU, smoke tests only)

```bash
make local
make health
```

A 3B model on CPU is adequate for wiring checks, **not** for results.

### MLflow UI (either path)

```
http://localhost:5000
```

---

## 2. Pull the judge model

The judge must come from a **different model family** than the candidates.
A judge from the same family as a candidate grades its own family, so
`assert_judge_independence()` will refuse to run in that case.

On the cluster, inside the running Ollama container:
```bash
ollama pull phi4:14b
```

To have the Slurm job pull it automatically on every submit, add this line to
the `for entry in \` list in `hpc/ollama-entrypoint.sh`:
```
  "phi4:14b|phi4:14b|" \
```
(or create a `models/Modelfile.judge-phi` and register it as a
`sprintsight-judge-phi` alias, matching what `judges/custom_llm_judge.py`
already expects).

**Note:** `--llm-grounding` additionally needs the judge tag present in
`MODEL_NUM_CTX` (`schemas/modelname.py`), or
`judges/citation_ground_custom_judge.py` raises. Without it the enrichment
is skipped with a warning; everything else still runs.

---

## 3. Sanity checks — no GPU, no model server

Run these first; they catch wiring breakage in seconds.

```bash
# Gold data is self-consistent (all 6 dimensions, overall == rubric mean)
python -c "import schemas.benchmark; print('gold OK')"
```

```bash
# Whole judge pipeline against a stub judge, with known-answer assertions
python -m research.eval.mlflow_judge_eval selftest
```

```bash
# Registered datasets and their hashes
python -m research.eval.cli list-datasets
```

```bash
# Static checks
python -m ruff check research/ judges/ schemas/ llmops/ services/
python -m mypy research/eval/mlflow_judge_eval.py schemas/benchmark.py
```

---

## 4. Phase A — candidate sweep (the expensive part)

One MLflow run per `(model × dataset × prompt × seed)`. **Record each printed
`run_id`** — the judge pass needs them.

**A1. Smoke test one model on one example before paying full cost:**
```bash
python -m research.eval.cli run --model sprintsight-qwen --dataset d1_fixtures \
    --subset high_performing --note "smoke test" --phase smoke
```

**A2. Synthetic sweep — pipeline validation only, never a report claim:**
```bash
for M in sprintsight-qwen sprintsight-mistral sprintsight-gemma; do
  python -m research.eval.cli run --model "$M" --dataset d1_fixtures \
      --prompt-version v1.0 --phase preliminary
done
```

**A3. Real sprints — this is what the report cites:**
```bash
for M in sprintsight-qwen sprintsight-mistral sprintsight-gemma sprintsight-llama31; do
  python -m research.eval.cli run --model "$M" --dataset d_real_sprints \
      --prompt-version v1.0 --phase final
done
```

**A4. Repeats for within-model consistency (only models that survived A3):**
```bash
for M in sprintsight-qwen sprintsight-mistral; do
  python -m research.eval.cli run --model "$M" --dataset d_real_sprints \
      --repeats 3 --prompt-version v1.0 --phase deep_eval
done
```

**A5. 32B models — HPC only, and run them alone.** At Q4 they occupy ~20 GB of
the 24 GB card, so nothing else can be resident:
```bash
for M in sprintsight-qwen25-32b sprintsight-coder-32b sprintsight-r1-32b; do
  python -m research.eval.cli run --model "$M" --dataset d_real_sprints \
      --prompt-version v1.0 --phase final
done
```

**A6. Ordering sanity harness** (different question: does the engine rank the
hand-crafted fixtures in the expected order?):
```bash
python -m research.validation_harness --models sprintsight-qwen sprintsight-mistral \
    --repeats 5 --out-dir research/validation_results
```

---

## 5. Phase B — judge pass

Reads the stored assessments from Phase A's MLflow artifacts, so the judged
artifact is byte-identical to what Phase A measured. Run it **after** the
sweep, never interleaved — that keeps one model family resident at a time.

```bash
OLLAMA_BASE_URL=http://localhost:11435/v1 \
python -m research.eval.mlflow_judge_eval evaluate \
    --run-id <PHASE_A_RUN_ID> \
    --judge-model phi4:14b \
    --phase final \
    --out-dir research/judge_eval_report
```

Repeat per Phase-A run. Useful flags:

| Flag | Effect |
|---|---|
| `--cot-mode two_stage` | default; an evidence-audit call precedes scoring, so the score is conditioned on committed reasoning. 2 calls per cell. |
| `--cot-mode inline` | half the calls, weaker reasoning guarantee. Do not mix the two in one comparison. |
| `--no-llm` | deterministic metrics only. Free, and the fallback when the Slurm job gets pre-empted. |
| `--metrics Code_Faithfulness Bug_Actionability` | restrict to named rubrics. |
| `--llm-grounding` | adds per-claim grounding from `judges/citation_ground_custom_judge.py`. |
| `--human-annotations <csv>` | enables the meta-evaluation (§7). |

Call budget, two-stage: `rows × 5 metrics × 2`. Three models × three real
sprints = 9 rows = **90 judge calls**.

---

## 6. Phase C — merge and analyse

**C1. Merge judge scores back into the Phase-A run:**
```bash
python -m research.eval.attach_judge_scores \
    --judge-file research/judge_eval_report/judge_scores_for_attach.csv \
    --run-id <PHASE_A_RUN_ID>
```

**C2. Tables, pairwise CIs and plots — judge-independent headline:**
```bash
python -m research.eval.cli analyze --experiment sprintsight-model-comparison \
    --filter 'tags.phase = "final"' --out-dir research/eval_report \
    --pairwise-metric overall_score
```

**C3. Same analysis with the judge metric as headline (needs C1):**
```bash
python -m research.eval.cli analyze --experiment sprintsight-model-comparison \
    --filter 'tags.phase = "final"' --out-dir research/eval_report_with_judge \
    --pairwise-metric judge_quality_score
```

**C4. Paired tests with multiplicity correction:**
```bash
python -m research.eval.mlflow_judge_eval compare \
    --run-id <PHASE_A_RUN_ID> --judge-model phi4:14b \
    --out-dir research/judge_eval_report
```

At n=5 the Wilcoxon test **cannot** reach p≤0.05 at any effect size; the
`min_attainable_p` column says so. Quote the bootstrap CI and Cliff's delta,
not the p-value.

---

## 7. Phase D — validate the judge (do not skip)

Without this, every judge number in §5 is unfalsifiable.

**D1. Human baseline.** Score a sample of assessments yourself on the same
1–5 rubric. CSV with `example_id`, `model`, and one column per metric:

```csv
example_id,model,Code_Faithfulness,Bug_Actionability,Technical_Correctness,Evidence_Specificity,Rubric_Adherence
esports_sp1,sprintsight-qwen,4,3,4,5,4
esports_sp1,sprintsight-mistral,2,2,3,2,2
```

Aim for ≥20 annotated rows; below 10 the coefficients are indicative only and
the report says so.

**D2. Agreement + judge card:**
```bash
python -m research.eval.mlflow_judge_eval calibrate \
    --run-id <PHASE_A_RUN_ID> --judge-model phi4:14b \
    --human-annotations research/eval/data/human_baseline.csv \
    --out-dir research/judge_eval_report
```

Reports Cohen's κ, quadratic-weighted κ, Spearman ρ, Kendall τ,
Krippendorff α, ICC(2,1) and signed bias, each with a bootstrap CI, plus a
`judge_card.md` datasheet.

**D3. Position-bias (pairwise, order-swapped):**
```bash
python -m research.eval.mlflow_judge_eval pairwise \
    --run-id <PHASE_A_RUN_ID> --judge-model phi4:14b \
    --out-dir research/judge_eval_report
```

If `position_bias_rate` exceeds ~0.2, do not report pairwise verdicts as a
model ranking.

**D4. Self-consistency and perturbation sensitivity:**
```bash
python -m research.eval.mlflow_judge_eval consistency \
    --run-id <PHASE_A_RUN_ID> --judge-model phi4:14b --replicates 3 \
    --metrics Code_Faithfulness --out-dir research/judge_eval_report
```

Costs `rows × metrics × 3 perturbations × replicates` calls — the most
expensive command here. Run it on a subset.

**Reporting thresholds:** per-example judge scores are quotable only when
intra-rater α ≥ 0.67 **and** quadratic κ ≥ 0.61. Below that, report aggregate
rankings with CIs and say per-example scores are unreliable.

---

## 8. Optional — judge logged traces instead of stored runs

For assessments produced by the live FastAPI service:

```python
from research.eval.mlflow_judge_eval import build_trace_scorers
from judges.run_judges import grade_accuracy_from_trace
scorers = [grade_accuracy_from_trace, *build_trace_scorers()]
```

```bash
MLFLOW_GENAI_EVAL_MAX_WORKERS=1 python -m judges.run_judges
```

`judges/run_judges.py` hardcodes trace IDs in `__main__` — edit them first.

---

## 9. Known blockers

1. **No human gold for real sprints.** `gold_by_fixture()` covers only the
   five synthetic fixtures. `load_records_from_run` **skips** `esports_sp1`,
   `ftms_sp1` and `tennis_sp1` with a warning, so Phases B–D currently only
   work on `d1_fixtures`. Judging real sprints requires authoring gold
   assessments for them — this is the single biggest gap.
2. **`d1_fixtures` is smoke-test only**, per its own description. It must not
   back a report claim.
3. **`schemas/cs203_groundtruth.py` is missing**, so `judges/run_judges.py`
   and `judges/citation_ground_custom_judge.py` are not importable
   (documented in `pyproject.toml`). §8 is blocked until it lands;
   `load_records_from_traces` falls back to a local trace filter.
4. **`cicd` has no variance.** All five golds score it 1 because no fixture
   has any CI artifact, so cicd cannot discriminate between models and will
   always be the "weakest dimension" that `Bug_Actionability` rewards
   targeting. Fixing this needs a fixture with real CI.
5. ~~**Real-sprint bundles are huge.**~~ **FIXED.** The judge was shown the
   first ~20 commits of the raw bundle while the candidate was shown 30
   *sampled* ones, so 27–29 of every 30 citable commits were invisible and
   would have scored as fabrications. `render_bundle_for_judge` now shows the
   union of `_select_representative_commits` across dimensions — the
   candidate's own evidence view — plus the precomputed aggregates. 0 of
   64–89 citable SHAs are now invisible on all three real sprints. File
   lists degrade before any commit is dropped, and `SPRINTSIGHT_JUDGE_NUM_CTX`
   stops Ollama silently truncating the result.
6. **All three real sprints share one `team_id`/`sprint_id`**
   (`579ad702…/sp1`), which looks like an export artifact. The trace path
   keys on `team_id`, so they are indistinguishable there.
7. **Gold `overall_score` changed** when cicd was added (e.g. 9.0 → 7.5).
   Any `grade_abs_error_overall` from before that is not comparable; tag new
   sweeps with a fresh `--phase`.

---

## 10. Where the outputs land

| Path | Contents |
|---|---|
| MLflow UI | runs, params, metrics, `judge_card.md`, figures, eval tables |
| `research/eval_report/` | comparison tables, pairwise CIs, plots |
| `research/eval_report_with_judge/` | same, headline = judge score |
| `research/judge_eval_report/` | `judge_eval_rows.csv`, `judge_calibration.csv`, `model_comparisons.csv`, `judge_scores_for_attach.csv`, `pairwise_comparisons.csv`, `consistency_probe.csv` |
| `research/validation_results/` | ordering-harness output |
| `audit_logs/*.txt` | raw Ollama request/response with `duration_ms` |
