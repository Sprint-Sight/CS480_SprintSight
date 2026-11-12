"""The judge study can judge sprints that have no human gold (the real sprints).

Real sprints have no gold assessment. Rather than inventing placeholder gold -- which three of the
five LLM rubrics would read as grading context -- a run over gold-free sprints runs only the
gold-free rubrics and leaves every gold-derived column empty. Synthetic (gold) runs are unchanged.
Only synthetic fixtures are used here: real-sprint exports hold student data and are not in the repo.
"""

import dataclasses
import logging

import mlflow
import pandas as pd
import pytest

from evaluation.offline import datasets
from evaluation.offline.judge_study import frame as frame_module
from evaluation.offline.judge_study import records as records_module
from evaluation.offline.judge_study.deterministic import numeric_grade_errors
from evaluation.offline.judge_study.frame import (
    NO_GOLD_REFERENCE,
    _metrics_for_gold,
    build_eval_frame,
    render_gold_for_judge,
    run_judge_evaluation,
)
from evaluation.offline.judge_study.records import (
    bundles_for_run,
    install_stub_judge,
    synthetic_records,
    uninstall_stub_judge,
)
from evaluation.offline.judge_study.specs import (
    GOLD_DEPENDENT_METRICS,
    GOLD_FREE_METRICS,
    JUDGE_METRIC_NAMES,
    JUDGE_METRIC_SPECS,
)
from llmops import mlflow_config


def _without_gold(records):
    return [dataclasses.replace(record, gold=None) for record in records]


def test_the_gold_dependent_rubrics_are_exactly_those_that_read_gold() -> None:
    reads_gold = {s.name for s in JUDGE_METRIC_SPECS if "gold_reference" in s.grading_context_columns}

    assert set(GOLD_DEPENDENT_METRICS) == reads_gold
    assert set(GOLD_FREE_METRICS) == set(JUDGE_METRIC_NAMES) - reads_gold
    assert GOLD_FREE_METRICS  # something can always be judged


def test_no_gold_renders_a_neutral_reference_not_placeholder_scores() -> None:
    assert render_gold_for_judge(None) == NO_GOLD_REFERENCE
    assert "out of 10" not in NO_GOLD_REFERENCE


def test_grade_errors_are_empty_without_gold() -> None:
    record = synthetic_records()[0]

    errors = numeric_grade_errors(record.candidate, None)

    assert errors and all(value is None for value in errors.values())


def test_eval_frame_leaves_every_gold_column_empty_without_gold() -> None:
    with_gold = synthetic_records()[:2]

    gold_frame = build_eval_frame(with_gold)
    free_frame = build_eval_frame(_without_gold(with_gold))

    assert (free_frame["target"] == "").all()
    assert (free_frame["gold_reference"] == NO_GOLD_REFERENCE).all()
    for column in ("rouge_l_vs_gold", "token_overlap_vs_gold", "gold_overall_score",
                   "grade_abs_error_code_quality", "grade_signed_error_overall"):
        assert free_frame[column].isna().all(), column
        assert gold_frame[column].notna().all(), column
    # Everything that does not depend on gold is computed the same way.
    for column in ("groundedness_rate", "citation_anchor_rate", "lint_warning_count", "prediction"):
        pd.testing.assert_series_equal(gold_frame[column], free_frame[column])


def test_rubric_selection_follows_gold_availability() -> None:
    records = synthetic_records()[:2]
    no_gold = _without_gold(records)

    assert _metrics_for_gold(records, None) == (True, None)
    assert _metrics_for_gold(records, ["Bug_Actionability"]) == (True, ["Bug_Actionability"])
    assert _metrics_for_gold(no_gold, None) == (False, list(GOLD_FREE_METRICS))
    assert _metrics_for_gold(no_gold, ["Code_Faithfulness", "Rubric_Adherence"]) == (
        False, ["Code_Faithfulness"],
    )
    with pytest.raises(ValueError, match="needs gold"):
        _metrics_for_gold(no_gold, ["Bug_Actionability"])
    with pytest.raises(ValueError, match="separate runs"):
        _metrics_for_gold([records[0], no_gold[1]], None)


def test_records_take_their_bundles_from_the_dataset_the_run_logged(monkeypatch, caplog) -> None:
    fixture = synthetic_records()[0].bundle
    item = datasets.DatasetItem(id="team_sprint-1", bundle=fixture)
    monkeypatch.setattr(datasets, "load_dataset", lambda name: ([item], "current-hash", None))

    assert bundles_for_run({"dataset_name": "d_real_sprints", "dataset_hash": "current-hash"}) == {
        "team_sprint-1": fixture
    }
    with caplog.at_level(logging.WARNING, logger=records_module.log.name):
        bundles_for_run({"dataset_name": "d_real_sprints", "dataset_hash": "old-hash"})
    assert "has changed since this run" in caplog.text
    # Runs from before the dataset name was logged were always over the synthetic fixtures.
    assert "high_performing" in bundles_for_run({})


@pytest.fixture
def scratch_mlflow(tmp_path, monkeypatch):
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    monkeypatch.setattr(mlflow_config, "_configured", True)
    monkeypatch.setattr(mlflow_config, "_experiment_ids", {})
    monkeypatch.chdir(tmp_path)
    install_stub_judge()
    yield
    uninstall_stub_judge()
    mlflow.set_tracking_uri(previous)


def test_a_gold_free_run_scores_only_the_gold_free_rubrics(scratch_mlflow, monkeypatch) -> None:
    monkeypatch.setattr(frame_module, "assert_judge_independence", lambda *a, **k: {})
    records = _without_gold(synthetic_records()[:2])

    _, enriched = run_judge_evaluation(records, experiment="judge-without-gold", cot_mode="inline")

    judged = {c.removeprefix("judge_") for c in enriched.columns
              if c.startswith("judge_") and c not in ("judge_quality_score", "judge_rationale",
                                                      "judge_composite")}
    assert judged == set(GOLD_FREE_METRICS)
    assert enriched["grade_signed_error_overall"].isna().all()
    params = mlflow.search_runs(experiment_names=["judge-without-gold"]).iloc[0]
    assert params["params.gold_available"] == "False"
    assert params["params.judge_metrics"] == ",".join(GOLD_FREE_METRICS)
