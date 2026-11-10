"""Judge scores reach the analysis layer in the shape the production judge actually writes."""

import json

import pandas as pd
import pytest

from research.eval.analysis import load_engine_results
from research.eval.attach_judge_scores import (
    judge_quality_score,
    load_judge_scores,
    merge_judge_scores,
)
from schemas.run_record import base_record


def judge_row(trace_id: str, timestamp: str = "2026-10-01T00:00:00+00:00", **scores) -> dict:
    return {"trace_id": trace_id, "team_id": "team-a", "sprint_id": "s1", "graded_by": "sprintsight-qwen",
            "judge_model": "sprintsight-judge-phi", "group": "no_gold", "judge_run_id": "jr",
            "timestamp": timestamp, "scores": scores}


def write_jsonl(path, rows) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ the quality score


def test_quality_prefers_the_rate_that_counts_dropped_fabrications() -> None:
    scores = {"citation_severity_weighted_rate_incl_dropped": 0.25, "citation_severity_weighted_rate": 0.1,
              "citation_hallucination_rate": 0.0}
    assert judge_quality_score(scores) == 0.75


def test_quality_falls_back_to_the_next_available_rate() -> None:
    assert judge_quality_score({"citation_severity_weighted_rate": 0.1}) == 0.9
    assert judge_quality_score({"citation_hallucination_rate": 0.2}) == 0.8


def test_quality_is_none_when_the_judge_produced_no_rate() -> None:
    assert judge_quality_score({}) is None
    assert judge_quality_score({"citation_hallucination_rate": None, "citation_count": 4}) is None
    assert judge_quality_score({"citation_hallucination_rate": float("nan")}) is None


# ------------------------------------------------------------------ reading judge files


def test_production_judge_rows_are_flattened(tmp_path) -> None:
    path = tmp_path / "raw_judge_results_exp_20261001.jsonl"
    write_jsonl(path, [judge_row("tr-1", citation_severity_weighted_rate_incl_dropped=0.2,
                                 citation_hallucination_rate=0.1, citation_count=12, citations_dropped_by_code=1)])

    frame = load_judge_scores(path)

    row = frame.iloc[0]
    assert row["trace_id"] == "tr-1" and row["judge_quality_score"] == 0.8
    assert row["judge_citation_count"] == 12 and row["judge_citation_hallucination_rate"] == 0.1
    assert "sprintsight-judge-phi" in row["judge_rationale"] and "dropped_by_code=1" in row["judge_rationale"]


def test_a_trace_judged_twice_keeps_only_its_latest_verdict(tmp_path) -> None:
    path = tmp_path / "raw_judge_results_x.jsonl"
    write_jsonl(path, [
        judge_row("tr-1", "2026-10-01T00:00:00+00:00", citation_hallucination_rate=0.5),
        judge_row("tr-1", "2026-10-02T00:00:00+00:00", citation_hallucination_rate=0.1),
    ])

    frame = load_judge_scores(path)

    assert len(frame) == 1 and frame.iloc[0]["judge_quality_score"] == 0.9


def test_the_original_csv_hand_off_still_loads(tmp_path) -> None:
    path = tmp_path / "judge.csv"
    pd.DataFrame([{"example_id": "e1", "judge_quality_score": 0.7, "judge_rationale": "ok"}]).to_csv(path, index=False)

    frame = load_judge_scores(path)

    assert frame.iloc[0]["example_id"] == "e1" and frame.iloc[0]["judge_quality_score"] == 0.7


# ------------------------------------------------------------------------- merging


def per_example(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame([{**base_record(), **row} for row in rows])


def test_rows_are_joined_on_the_trace_id(tmp_path) -> None:
    path = tmp_path / "j.jsonl"
    write_jsonl(path, [judge_row("tr-2", citation_hallucination_rate=0.0)])
    rows = per_example({"example_id": "e1", "trace_id": "tr-1"}, {"example_id": "e2", "trace_id": "tr-2"})

    merged = merge_judge_scores(rows, load_judge_scores(path))

    by_example = merged.set_index("example_id")["judge_quality_score"]
    assert by_example["e2"] == 1.0
    assert pd.isna(by_example["e1"])  # not judged: kept, not dropped
    assert len(merged) == 2


def test_stale_judge_columns_are_replaced_not_duplicated(tmp_path) -> None:
    path = tmp_path / "j.jsonl"
    write_jsonl(path, [judge_row("tr-1", citation_hallucination_rate=0.2)])
    rows = per_example({"example_id": "e1", "trace_id": "tr-1", "judge_quality_score": 0.1, "judge_rationale": "old"})

    merged = merge_judge_scores(rows, load_judge_scores(path))

    assert list(merged.columns).count("judge_quality_score") == 1
    assert merged.iloc[0]["judge_quality_score"] == 0.8 and merged.iloc[0]["judge_rationale"] != "old"


def test_without_trace_ids_it_falls_back_to_example_id(tmp_path) -> None:
    path = tmp_path / "judge.csv"
    pd.DataFrame([{"example_id": "e1", "judge_quality_score": 0.6}]).to_csv(path, index=False)
    rows = per_example({"example_id": "e1"}, {"example_id": "e2"})

    merged = merge_judge_scores(rows, load_judge_scores(path))

    assert merged.set_index("example_id")["judge_quality_score"]["e1"] == 0.6


def test_a_judge_file_that_cannot_be_joined_is_an_error(tmp_path) -> None:
    path = tmp_path / "judge.csv"
    pd.DataFrame([{"something_else": 1}]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        merge_judge_scores(per_example({"example_id": "e1"}), load_judge_scores(path))


# --------------------------------------------------- production runs in the analysis layer


def test_engine_results_and_judge_verdicts_load_as_one_frame(tmp_path) -> None:
    legacy_run = {"team_id": "team-a", "sprint_id": "s1", "model": "sprintsight-qwen", "run_id": "r1",
                  "trace_id": "tr-1", "overall_score": 7.0, "duration_seconds": 100.0,
                  "dimension_scores": {"code_quality": 7, "testing": 7, "documentation": 7,
                                       "requirements": 7, "collaboration": 7, "cicd": 7},
                  "failed_dimensions": {}, "prompt_versions": {}}
    write_jsonl(tmp_path / "raw_results_exp_20261001.jsonl", [legacy_run])
    write_jsonl(tmp_path / "raw_judge_results_exp_20261001.jsonl",
                [judge_row("tr-1", citation_severity_weighted_rate_incl_dropped=0.1)])

    frame = load_engine_results(tmp_path)

    row = frame.iloc[0]
    assert (row["model"], row["example_id"], row["latency_s"]) == ("sprintsight-qwen", "team-a|s1", 100.0)
    assert row["format_valid"] == True
    assert row["judge_quality_score"] == 0.9


def test_an_empty_results_directory_gives_an_empty_frame(tmp_path) -> None:
    assert load_engine_results(tmp_path).empty
