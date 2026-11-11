"""One row shape for the research runner and the engine, and upgrading rows from before it."""

from types import SimpleNamespace
from typing import Any

from prompts.dimension_criteria import DIMENSIONS
from schemas.run_record import (
    base_record,
    normalize_run_record,
    score_fields,
    validity_fields,
)


def _score(value: int, *, failed: bool = False) -> SimpleNamespace:
    return SimpleNamespace(score=value, evaluation_failed=failed)


def test_the_base_record_has_every_column_a_consumer_reads() -> None:
    record = base_record()
    for key in ("example_id", "repeat_index", "model", "trace_id", "team_id", "sprint_id",
                "format_valid", "failed_dimension_names", "failure_classes", "overall_score",
                "groundedness_rate", "citations_dropped", "latency_s", "judge_quality_score"):
        assert key in record
    assert all(f"score_{dimension}" in record for dimension in DIMENSIONS)


def test_base_records_do_not_share_mutable_state() -> None:
    first, second = base_record(), base_record()
    first["failure_classes"]["testing"] = "timeout"
    first["failed_dimension_names"].append("x")
    assert second["failure_classes"] == {} and "x" not in second["failed_dimension_names"]


def test_validity_counts_present_failed_and_missing_dimensions() -> None:
    scores: dict[str, Any] = {name: _score(8) for name in DIMENSIONS}
    scores["testing"] = _score(1, failed=True)
    scores["cicd"] = None

    fields = validity_fields(scores)

    assert (fields["dimensions_present"], fields["dimensions_failed"], fields["dimensions_missing"]) == (4, 1, 1)
    assert fields["format_valid"] is False
    assert fields["failed_dimension_names"] == ["testing", "cicd"]
    assert fields["dimension_completion_rate"] == 4 / 6


def test_score_fields_never_include_a_failed_dimensions_placeholder() -> None:
    scores: dict[str, Any] = {name: _score(8) for name in DIMENSIONS}
    scores["testing"] = _score(1, failed=True)

    fields = score_fields(scores)

    assert fields["score_testing"] is None
    assert fields["rubric_mean"] == 8.0 and fields["rubric_min"] == 8.0
    assert fields["raw_rubric_average"] == 8.0


def test_score_fields_with_nothing_scored_are_all_none() -> None:
    fields = score_fields({})
    assert fields["rubric_mean"] is None and fields["score_testing"] is None


def _legacy_engine_row() -> dict:
    return {
        "team_id": "team-a", "sprint_id": "s1", "model": "sprintsight-qwen", "run_id": "r1", "trace_id": "tr-1",
        "overall_score": 7.5,
        "dimension_scores": {"code_quality": 8, "testing": None, "documentation": 7, "requirements": 8,
                             "collaboration": 7, "cicd": 7},
        "failed_dimensions": {"testing": "timeout: ReadTimeout: no answer"},
        "prompt_versions": {"Evaluate_testing": 3},
        "duration_seconds": 412.5,
        "timestamp": "2026-10-01T00:00:00+00:00",
    }


def test_a_row_from_the_old_engine_shape_is_upgraded() -> None:
    record = normalize_run_record(_legacy_engine_row())

    assert record["score_code_quality"] == 8.0 and record["score_testing"] is None
    assert record["latency_s"] == 412.5
    assert record["example_id"] == "team-a|s1"
    assert record["failure_classes"] == {"testing": "timeout"}
    assert record["failure_details"] == {"testing": "ReadTimeout: no answer"}
    assert (record["dimensions_present"], record["dimensions_failed"]) == (5, 1)
    assert record["failed_dimension_names"] == ["testing"]
    assert record["format_valid"] is False
    assert "failed_dimensions" not in record and "dimension_scores" not in record


def test_legacy_failure_text_without_a_class_keeps_its_detail() -> None:
    row = _legacy_engine_row()
    row["failed_dimensions"] = {"testing": "Some old error text: with a colon"}

    record = normalize_run_record(row)

    assert record["failure_classes"] == {}
    assert record["failure_details"] == {"testing": "Some old error text: with a colon"}


def test_a_current_row_passes_through_unchanged() -> None:
    row = base_record()
    row.update(example_id="fixture_alpha", repeat_index=2, model="m", overall_score=6.0,
               format_valid=True, dimensions_present=6, dimensions_failed=0, dimensions_missing=0,
               failed_dimension_names=[], latency_s=10.0)

    assert normalize_run_record(row) == row


def test_extra_columns_from_other_tools_are_kept() -> None:
    record = normalize_run_record({**base_record(), "tokens_total": 1234, "llm_http_calls": 7})
    assert record["tokens_total"] == 1234 and record["llm_http_calls"] == 7
