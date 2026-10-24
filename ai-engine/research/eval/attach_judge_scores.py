"""Attach external judge scores to the per_example rows of an existing run.

Scope: the judge pipeline itself produces one CSV/JSONL with
columns:

    mlflow_run_id, example_id, repeat_index, judge_quality_score, judge_rationale

and this script downloads the matching run's per_example.jsonl, merges
the judge columns in by key, re-uploads the merged file, and logs
`judge_quality_score_mean` as a new metric on the same run.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import mlflow
import pandas as pd

log = logging.getLogger(__name__)


def attach(judge_csv: Path, run_id: str, cache_dir: str | Path = ".eval_cache") -> None:
    client = mlflow.tracking.MlflowClient()
    local_dir = Path(cache_dir) / f"attach_{run_id}"
    local_dir.mkdir(parents=True, exist_ok=True)

    found = None
    for art in client.list_artifacts(run_id):
        if art.path.endswith("per_example.jsonl"):
            found = client.download_artifacts(run_id, art.path, str(local_dir))
            break
    if not found:
        raise FileNotFoundError(f"Run {run_id} has no per_example.jsonl artifact.")

    with Path(found).open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    df = pd.DataFrame(rows)

    judge = pd.read_csv(judge_csv) if str(judge_csv).endswith(".csv") else pd.read_json(judge_csv, lines=True)
    required = {"example_id", "judge_quality_score"}
    missing = required - set(judge.columns)
    if missing:
        raise ValueError(f"Judge file is missing required columns: {missing}")

    # Overwrite the placeholder None values; keep repeat_index in the key
    # so a judge with per-repeat scores still merges correctly.
    merge_keys = ["example_id"]
    if "repeat_index" in judge.columns:
        merge_keys.append("repeat_index")
    df = df.drop(columns=["judge_quality_score", "judge_rationale"], errors="ignore")
    merged = df.merge(judge, on=merge_keys, how="left")

    merged_path = local_dir / "per_example.jsonl"
    with merged_path.open("w", encoding="utf-8") as f:
        for row in merged.to_dict(orient="records"):
            f.write(json.dumps(row, default=str) + "\n")

    with mlflow.start_run(run_id=run_id):
        mlflow.log_artifact(str(merged_path))
        mean_judge = pd.to_numeric(merged["judge_quality_score"], errors="coerce").dropna()
        if not mean_judge.empty:
            mlflow.log_metric("judge_quality_score_mean", float(mean_judge.mean()))
            mlflow.log_metric("judge_quality_score_n", int(mean_judge.shape[0]))
        mlflow.set_tag("judge_attached", "true")
    log.info("Attached judge scores to run %s (n=%d).", run_id, len(merged))


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-file", required=True, type=Path,
                        help="CSV or JSONL with at least example_id and judge_quality_score columns.")
    parser.add_argument("--run-id", required=True, help="MLflow run_id to attach to.")
    args = parser.parse_args()
    attach(args.judge_file, args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
