import json, logging, math, mlflow, re, threading
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from prompts.dimension_criteria import DIMENSIONS

log = logging.getLogger("sprintsight.save_results")

RESULTS_DIRECTORY = Path(__file__).resolve().parent.parent / "results" 
_SESSION_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") # 1 file per run, so a judge can see the new traces and not be confused by old ones. The judge only looks at traces in the same experiment as the challenger prompt version.
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
    teams = {}
    for team in sorted({r["team_id"] for r in rows}):
        t = [r for r in rows if r["team_id"] == team]
        dim_scores = {d: [r["dimension_scores"][d] for r in t if r["dimension_scores"].get(d) is not None]
                      for d in DIMENSIONS}
        teams[team] = {
            "runs": len(t),
            "mean_overall_score": round(mean(r["overall_score"] for r in t), 3),
            "mean_dimension_scores": {d: round(mean(v), 3) if v else None for d, v in dim_scores.items()},
            "runs_with_failed_dimensions": sum(1 for r in t if r["failed_dimensions"]),
            "trace_ids": [r["trace_id"] for r in t],
        }
    return {**meta, "total_runs": len(rows), "teams": teams}

# Summarize the judge's verdicts for a single trace, including per-dimension hallucination rates, a row per judged citation.
def _summarize_judge(rows: list[dict], meta: dict) -> dict:
    cols = sorted({c for r in rows for c, v in r['scores'].items() if isinstance(v, (int, float))})

# Append this run to the raw jsonl, rebuild the summary, and attach both to the ACTIVE MLflow run.
# Call it inside `with mlflow.start_run(...)`. Never raises: results are a by-product of grading.
def save_run_results(*, experiment_name: str, model_name: str, team_id: str, sprint_id: str,
                     trace_id: str, run_id: str, overall_score: float,
                     scores_by_dim: dict, failed_dimensions: dict,
                     prompt_versions: dict, duration_seconds: float) -> tuple[Path, Path]:
    label = _slug(experiment_name)
    raw_path = RESULTS_DIRECTORY / f"raw_results_{label}_{_SESSION_TS}.jsonl"
    summary_path = RESULTS_DIRECTORY / f"summary_{label}_{_SESSION_TS}.json"
    row = {
        "team_id": team_id, "sprint_id": sprint_id, "model": model_name, "run_id": run_id, "trace_id": trace_id,
        "overall_score": overall_score,
        "dimension_scores": {d: (None if s.evaluation_failed else s.score) for d, s in scores_by_dim.items()},
        "failed_dimensions": failed_dimensions,
        "prompt_versions": prompt_versions,
        "duration_seconds": round(duration_seconds, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
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
        # Log artifact attaches to active run
        mlflow.log_artifact(str(raw_path), artifact_path="trial_results")
        mlflow.log_artifact(str(summary_path), artifact_path="trial_results")
        print(f"Raw results: {raw_path}\nSummary:     {summary_path}")

    except Exception:
        log.warning("Could not save/log trial results for %s", trace_id, exc_info=True)

    return raw_path, summary_path

def save_judge_results(*, experiment_name: str, judge_model: str, group_name: str, run_id: str,
                       result_df, trace_meta: dict[str, dict]) -> tuple[Path, Path]:
    """One row per judged trace. Call it INSIDE the judge's `with mlflow.start_run(...)`, so the
    files attach to the judge run. Never raises: judging has already succeeded by this point."""
    label = _slug(experiment_name)
    raw_path = RESULTS_DIRECTORY / f"raw_judge_results_{label}_{_SESSION_TS}.jsonl"
    summary_path = RESULTS_DIRECTORY / f"summary_judge_{label}_{_SESSION_TS}.json"
    ts = datetime.now(timezone.utc).isoformat()
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
    try:
        with _LOCK:
            RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
            with raw_path.open("a", encoding="utf-8") as f:
                for r in new_rows:
                    f.write(json.dumps(r, default=str) + "\n")
            rows = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            summary = _summarize_judge(rows, {"experiment": experiment_name, "judge_model": judge_model, "session": _SESSION_TS})
            tmp = summary_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            tmp.replace(summary_path)
        # Log artifact attaches to active judge run
        mlflow.log_artifact(str(raw_path), artifact_path="judge_results")
        mlflow.log_artifact(str(summary_path), artifact_path="judge_results")
        print(f"Judge raw results: {raw_path}\nJudge summary:     {summary_path}")

    except Exception:
        log.warning("Could not save/log judge results for run %s", run_id, exc_info=True)

    return raw_path, summary_path