import json
import logging
import math
import re
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

import mlflow

from prompts.dimension_criteria import DIMENSIONS
from schemas.run_record import (
    base_record,
    normalize_run_record,
    score_fields,
    validity_fields,
)

log = logging.getLogger("sprintsight.save_results")

RESULTS_DIRECTORY = Path(__file__).resolve().parent.parent / "results" 
_SESSION_TS = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") # 1 file per run, so a judge can see the new traces and not be confused by old ones. The judge only looks at traces in the same experiment as the challenger prompt version.
_LOCK = threading.Lock()  # for concurrent writes to the same file

def _slug(text: str):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") # experiment name contains slashes

# result_df cells are numpy types / NaN
# json.dumps(default=str) converts numbers -> strings
def _plain(v):
    if hasattr(v, "item"): # numpy scalar
        v = v.item()
    return None if isinstance(v, float) and math.isnan(v) else v

def _summarize_raw_results(rows: list[dict], meta: dict) -> dict:
    rows = [normalize_run_record(r) for r in rows]  # files written before the unified schema still summarise
    teams = {}
    for team in sorted({r["team_id"] for r in rows if r["team_id"]}):
        t = [r for r in rows if r["team_id"] == team]
        dim_scores = {d: [r[f"score_{d}"] for r in t if r[f"score_{d}"] is not None] for d in DIMENSIONS}
        overall = [r["overall_score"] for r in t if r["overall_score"] is not None]
        teams[team] = {
            "runs": len(t),
            "mean_overall_score": round(mean(overall), 3) if overall else None,
            "mean_dimension_scores": {d: round(mean(v), 3) if v else None for d, v in dim_scores.items()},
            "runs_with_failed_dimensions": sum(1 for r in t if r["dimensions_failed"] or r["dimensions_missing"]),
            "failure_classes": dict(Counter(c for r in t for c in r["failure_classes"].values())),
            "trace_ids": [r["trace_id"] for r in t],
        }
    return {**meta, "total_runs": len(rows), "teams": teams}

# Summarize the judge's verdicts for a single trace, including per-dimension hallucination rates, a row per judged citation.
# def _summarize_judge(rows: list[dict], meta: dict) -> dict:
#     cols = sorted({c for r in rows for c, v in r['scores'].items() if isinstance(v, (int, float))})

# Append this run to the raw jsonl, rebuild the summary, and attach both to the ACTIVE MLflow run.
# Call it inside `with mlflow.start_run(...)`. Never raises: results are a by-product of grading.
def save_run_results(*, experiment_name: str, model_name: str, team_id: str, sprint_id: str,
                     trace_id: str, run_id: str, overall_score: float,
                     scores_by_dim: dict, failed_dimensions: dict,
                     prompt_versions: dict, duration_seconds: float,
                     failure_classes: dict | None = None) -> tuple[Path, Path]:
    label = _slug(experiment_name)
    raw_path = RESULTS_DIRECTORY / f"raw_results_{label}_{_SESSION_TS}.jsonl"
    summary_path = RESULTS_DIRECTORY / f"summary_{label}_{_SESSION_TS}.json"
    # The same row shape the research runner writes to per_example.jsonl (schemas/run_record.py),
    # so the analysis layer can read production runs and benchmark runs with one loader.
    row = base_record()
    row.update(
        example_id=f"{team_id}|{sprint_id}", repeat_index=0, model=model_name,
        team_id=team_id, sprint_id=sprint_id, run_id=run_id, trace_id=trace_id,
        overall_score=overall_score,
        failure_classes=failure_classes or {},
        failure_details=failed_dimensions,   # {dimension: "<class>: <full error text>"}
        prompt_versions=prompt_versions,
        latency_s=round(duration_seconds, 2),
        timestamp=datetime.now(UTC).isoformat(),
    )
    row.update(validity_fields(scores_by_dim))
    row.update(score_fields(scores_by_dim))
    try:
        with _LOCK: # concurrent writes to the same file
            RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with raw_path.open("a", encoding="utf-8") as f: # append = survives interruption
                f.write(json.dumps(row, default=str) + "\n")
            rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            summary = _summarize_raw_results(rows, {"experiment": experiment_name, "model": model_name, "session": _SESSION_TS})
            tmp = summary_path.with_suffix(".json.tmp")                           # write-then-rename: never a half-written summary
            tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            tmp.replace(summary_path)
        # Attach to the grading run by id. The fluent mlflow.log_artifact needs an active run,
        # and evaluate_sprint no longer opens one (it would create a stray run instead).
        client = mlflow.MlflowClient()
        client.log_artifact(run_id, str(raw_path), "trial_results")
        client.log_artifact(run_id, str(summary_path), "trial_results")
        print(f"Raw results: {raw_path}\nSummary:     {summary_path}")

    except Exception:
        log.warning("Could not save/log trial results for %s", trace_id, exc_info=True)

    return raw_path, summary_path

def save_judge_results(*, experiment_name: str, judge_model: str, group_name: str, run_id: str,
                       result_df, trace_meta: dict[str, dict]) -> Path:
    """One row per judged trace. Call it INSIDE the judge's `with mlflow.start_run(...)`, so the
    files attach to the judge run. Never raises: judging has already succeeded by this point."""
    label = _slug(experiment_name)
    raw_path = RESULTS_DIRECTORY / f"raw_judge_results_{label}_{_SESSION_TS}.jsonl"
    # summary_path = RESULTS_DIRECTORY / f"summary_judge_{label}_{_SESSION_TS}.json"
    ts = datetime.now(UTC).isoformat()
    new_rows = []
    for _, df_row in result_df.iterrows():
        tid = df_row["trace_id"]
        meta = trace_meta.get(tid, {})
        new_rows.append({
            "trace_id": tid,                         # the GRADER's trace: join key to raw_results_*.jsonl
            "team_id": meta.get("team_id"), "sprint_id": meta.get("sprint_id"), "graded_by": meta.get("model"),
            "judge_model": judge_model, "group": group_name, "judge_run_id": run_id, "timestamp": ts,
            # every "<scorer>/value" column, e.g. citation_hallucination_rate, grade_penalised_mae
            "scores": {c[: -len("/value")]: _plain(df_row[c]) for c in result_df.columns if c.endswith("/value")},
        })
    try: # concurrent writes to the same file
        with _LOCK:
            RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with raw_path.open("a", encoding="utf-8") as f:
                for r in new_rows: # write 1 row per judged trace
                    f.write(json.dumps(r, default=str) + "\n")
            # rows = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            # summary = _summarize_judge(rows, {"experiment": experiment_name, "judge_model": judge_model, "session": _SESSION_TS})
            # tmp = summary_path.with_suffix(".json.tmp")
            # tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            # tmp.replace(summary_path)
        # Log artifact attaches to active judge run
        mlflow.log_artifact(str(raw_path), artifact_path="judge_results")
        #mlflow.log_artifact(str(summary_path), artifact_path="judge_results")
        print(f"Judge raw results: {raw_path}") # \nJudge summary:     {summary_path}")

    except Exception:
        log.warning("Could not save/log judge results for run %s", run_id, exc_info=True)

    return raw_path #, summary_path