"""One row shape for "what happened in one assessment run".

Two producers wrote rows of different shapes for the same thing:

  * the research runner's `per_example.jsonl` (evaluation/offline): flat `score_<dim>`,
    `failed_dimension_names`, `latency_s`, keyed by `example_id` / `repeat_index` / `model`;
  * the engine's `raw_results_*.jsonl` (services/save_results): a nested `dimension_scores`
    dict, `failed_dimensions` as {dimension: error text}, `duration_seconds`, keyed by
    `trace_id`.

The analysis layer only understood the first, so production runs never reached it, and the
two sets of fields had to be reconciled by hand. Both producers now start from
`base_record()` (every key present, so a column can never be silently missing) and
`normalize_run_record()` upgrades rows written before this existed, so old artifacts and
result files keep loading.

Pure Python on purpose: no MLflow, no pandas, importable from the engine and from research.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from prompts.dimension_criteria import DIMENSIONS

from schemas.failure_class import FailureClass

_FAILURE_CLASSES = {failure_class.value for failure_class in FailureClass}


def base_record() -> dict[str, Any]:
    """Every field of a run row, at its 'nothing happened' value."""
    record: dict[str, Any] = {
        # identity: `trace_id` joins to the judge verdict, `example_id` + `repeat_index` to a dataset
        "example_id": None,
        "repeat_index": None,
        "model": None,
        "trace_id": None,
        "run_id": None,
        "team_id": None,
        "sprint_id": None,
        "timestamp": None,
        # did it produce a usable assessment
        "format_valid": False,
        "dimensions_present": 0,
        "dimensions_failed": 0,
        "dimensions_missing": len(DIMENSIONS),
        "dimensions_total": len(DIMENSIONS),
        "dimension_completion_rate": 0.0,
        "failed_dimension_names": list(DIMENSIONS),
        "failure_classes": {},   # dimension -> schemas.failure_class.FailureClass value
        "failure_details": {},   # dimension -> full error text
        # scores
        "overall_score": None,
        "rubric_mean": None,
        "rubric_min": None,
        "rubric_max": None,
        "raw_rubric_average": None,
        # grounding (code-level): dropped citations count as ungrounded, see evaluation/offline/metrics
        "groundedness_rate": None,
        "groundedness_citations_total": 0,
        "groundedness_citations_grounded": 0,
        "citations_dropped": 0,
        # performance / provenance
        "latency_s": None,
        "prompt_versions": {},
        "error": None,
        # judge slot: filled by evaluation/offline/attach_judge_scores.py
        "judge_quality_score": None,
        "judge_rationale": None,
    }
    for dimension in DIMENSIONS:
        record[f"score_{dimension}"] = None
    return record


def _evaluation_failed(score: Any) -> bool:
    if isinstance(score, Mapping):
        return bool(score.get("evaluation_failed"))
    return bool(getattr(score, "evaluation_failed", False))


def validity_fields(scores: Mapping[str, Any]) -> dict[str, Any]:
    """Which dimensions came back scored, failed, or missing. `scores` maps a dimension name
    to its score object (or mapping, or None). `format_valid` needs ALL dimensions scored."""
    present, failed, missing = [], [], []
    for dimension in DIMENSIONS:
        score = scores.get(dimension)
        if score is None:
            missing.append(dimension)
        elif _evaluation_failed(score):
            failed.append(dimension)
        else:
            present.append(dimension)
    return {
        "dimensions_present": len(present),
        "dimensions_failed": len(failed),
        "dimensions_missing": len(missing),
        "dimensions_total": len(DIMENSIONS),
        "dimension_completion_rate": len(present) / len(DIMENSIONS),
        "format_valid": len(present) == len(DIMENSIONS),
        "failed_dimension_names": failed + missing,
    }


def _value(score: Any) -> float | None:
    raw = score.get("score") if isinstance(score, Mapping) else getattr(score, "score", None)
    return float(raw) if isinstance(raw, (int, float)) else None


def score_fields(scores: Mapping[str, Any]) -> dict[str, Any]:
    """`score_<dim>` for every scored dimension (None for failed or missing ones) and the
    rubric mean/min/max. A failed dimension's placeholder score is never included."""
    fields: dict[str, Any] = {}
    values: list[float] = []
    for dimension in DIMENSIONS:
        score = scores.get(dimension)
        value = None if score is None or _evaluation_failed(score) else _value(score)
        fields[f"score_{dimension}"] = value
        if value is not None:
            values.append(value)
    mean = sum(values) / len(values) if values else None
    fields.update(
        rubric_mean=mean,
        rubric_min=min(values) if values else None,
        rubric_max=max(values) if values else None,
        raw_rubric_average=mean,  # unrounded on purpose: overall_score is rounded to 2dp upstream
    )
    return fields


def _split_failure_text(text: str) -> tuple[str | None, str]:
    """'timeout: ReadTimeout: ...' -> ('timeout', 'ReadTimeout: ...'); legacy text has no class."""
    head, separator, rest = text.partition(": ")
    if separator and head in _FAILURE_CLASSES:
        return head, rest
    return None, text


def normalize_run_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Upgrade a row from either legacy shape (or the current one) to the unified shape."""
    record = base_record()
    legacy_keys = {"dimension_scores", "failed_dimensions", "duration_seconds"}
    record.update({key: value for key, value in row.items() if key not in legacy_keys})

    nested_scores = row.get("dimension_scores")
    if isinstance(nested_scores, Mapping):  # raw_results_*.jsonl
        for dimension in DIMENSIONS:
            value = nested_scores.get(dimension)
            record[f"score_{dimension}"] = float(value) if isinstance(value, (int, float)) else None

    failed = row.get("failed_dimensions")
    if isinstance(failed, Mapping):  # {dimension: error text}
        classes, details = dict(record["failure_classes"]), dict(record["failure_details"])
        for dimension, text in failed.items():
            failure_class, detail = _split_failure_text(str(text))
            if failure_class:
                classes.setdefault(dimension, failure_class)
            details.setdefault(dimension, detail)
        record.update(failure_classes=classes, failure_details=details)

    if record["latency_s"] is None and row.get("duration_seconds") is not None:
        record["latency_s"] = row["duration_seconds"]
    if record["example_id"] is None and record["team_id"] and record["sprint_id"]:
        record["example_id"] = f"{record['team_id']}|{record['sprint_id']}"

    if "dimensions_present" not in row and isinstance(nested_scores, Mapping):
        # legacy engine row: derive validity from what it did record
        failed_names = set(failed) if isinstance(failed, Mapping) else set()
        stand_in: dict[str, Any] = {
            dimension: (
                {"score": record[f"score_{dimension}"], "evaluation_failed": dimension in failed_names}
                if record[f"score_{dimension}"] is not None or dimension in failed_names
                else None
            )
            for dimension in DIMENSIONS
        }
        record.update(validity_fields(stand_in))
    return record
