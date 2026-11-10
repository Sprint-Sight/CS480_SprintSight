"""Attach judge scores to the per_example rows of an existing run.

Two judge file shapes are understood:

  * the production judge's `raw_judge_results_*.jsonl` (services/save_results.save_judge_results):
    one row per judged trace, `{"trace_id", "judge_model", "judge_run_id", "timestamp",
    "scores": {"citation_severity_weighted_rate_incl_dropped": ..., ...}}`. It is joined to
    the run's rows on `trace_id` and `judge_quality_score` is derived from it (see
    `judge_quality_score`).
  * the original hand-off CSV/JSONL with `example_id` and `judge_quality_score` columns
    (optionally `repeat_index`, `judge_rationale`), joined on `example_id`.

This used to understand only the second shape, which nothing in the repo produced, so the
`judge_quality_score` column stayed empty for every run.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd

log = logging.getLogger(__name__)

# Judge scores that describe a rate of *bad* citations, best first. judge_quality_score is
# 1 minus the first one present, so higher is better like every other quality column.
_QUALITY_SOURCES = (
    "citation_severity_weighted_rate_incl_dropped",  # counts code-removed fabrications too
    "citation_severity_weighted_rate",
    "citation_hallucination_rate",
)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if math.isnan(value) else float(value)


def judge_quality_score(scores: Mapping[str, Any]) -> float | None:
    """Higher-is-better quality in [0, 1] from a judged trace's scores, or None if the judge
    produced none of the rates (e.g. its call failed)."""
    for key in _QUALITY_SOURCES:
        rate = _number(scores.get(key))
        if rate is not None:
            return round(1.0 - rate, 4)
    return None


def _rationale(scores: Mapping[str, Any], judge_model: str | None) -> str:
    parts = [f"judge={judge_model}"] if judge_model else []
    for key in ("citation_severity_weighted_rate_incl_dropped", "citation_hallucination_rate",
                "citations_dropped_by_code", "citation_count"):
        value = _number(scores.get(key))
        if value is not None:
            parts.append(f"{key.removeprefix('citation_')}={value:g}")
    return "; ".join(parts)


def load_judge_scores(paths: Iterable[str | Path] | str | Path) -> pd.DataFrame:
    """Read judge output (production JSONL, or the original CSV/JSONL) into one frame.

    A trace judged more than once (a re-judge) keeps only its latest row."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    rows: list[dict[str, Any]] = []
    for path in map(Path, paths):
        if path.suffix == ".csv":
            rows.extend({str(key): value for key, value in record.items()}
                        for record in pd.read_csv(path).to_dict(orient="records"))
        else:
            rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    flat: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row.get("scores"), Mapping):  # production judge
            scores = row["scores"]
            flat.append({
                "trace_id": row.get("trace_id"),
                "judge_model": row.get("judge_model"),
                "judge_timestamp": row.get("timestamp"),
                "judge_quality_score": judge_quality_score(scores),
                "judge_rationale": _rationale(scores, row.get("judge_model")),
                **{f"judge_{name}": _number(value) for name, value in scores.items() if _number(value) is not None},
            })
        else:  # original hand-off shape
            flat.append(dict(row))
    frame = pd.DataFrame(flat)
    if "trace_id" in frame and "judge_timestamp" in frame and frame["trace_id"].notna().any():
        frame = (frame.sort_values("judge_timestamp", na_position="first")
                 .drop_duplicates("trace_id", keep="last").reset_index(drop=True))
    return frame


def merge_judge_scores(per_example: pd.DataFrame, judge: pd.DataFrame) -> pd.DataFrame:
    """Overwrite the judge columns of `per_example` from `judge`.

    Joined on `trace_id` when both sides carry it (rows the judge scored by trace), otherwise on
    `example_id` (+ `repeat_index` when the judge file has it). Rows the judge did not cover
    keep empty judge columns; they are never dropped."""
    judge_columns = [c for c in judge.columns if c.startswith("judge_") or c == "judge_quality_score"]
    use_trace = ("trace_id" in judge and judge["trace_id"].notna().any()
                 and "trace_id" in per_example and per_example["trace_id"].notna().any())
    if use_trace:
        keys = ["trace_id"]
    else:
        required = {"example_id", "judge_quality_score"}
        if missing := required - set(judge.columns):
            raise ValueError(f"Judge file is missing required columns: {missing}")
        keys = ["example_id"] + (["repeat_index"] if "repeat_index" in judge and "repeat_index" in per_example else [])
    judge = judge[keys + judge_columns].drop_duplicates(keys, keep="last")
    base = per_example.drop(columns=[c for c in judge_columns if c in per_example], errors="ignore")
    return base.merge(judge, on=keys, how="left")


def attach(judge_file: Path, run_id: str, cache_dir: str | Path = ".eval_cache") -> None:
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
        df = pd.DataFrame([json.loads(line) for line in fh if line.strip()])

    merged = merge_judge_scores(df, load_judge_scores(judge_file))
    covered = int(pd.to_numeric(merged["judge_quality_score"], errors="coerce").notna().sum())

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
    log.info("Attached judge scores to run %s (%d of %d rows covered).", run_id, covered, len(merged))


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-file", required=True, type=Path,
                        help="raw_judge_results_*.jsonl from the engine, or a CSV/JSONL with "
                             "example_id and judge_quality_score columns.")
    parser.add_argument("--run-id", required=True, help="MLflow run_id to attach to.")
    args = parser.parse_args()
    attach(args.judge_file, args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
