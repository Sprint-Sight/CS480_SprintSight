"""The engine's result files: unified rows, artifacts logged by run id."""

import json

import pytest

from prompts.dimension_criteria import DIMENSIONS
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.run_record import base_record
from services import save_results

LOGGED: list = []


class FakeClient:
    def log_artifact(self, run_id, local_path, artifact_path=None):
        LOGGED.append((run_id, artifact_path, local_path))


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(save_results, "RESULTS_DIRECTORY", tmp_path)
    monkeypatch.setattr(save_results.mlflow, "MlflowClient", FakeClient)
    LOGGED.clear()
    return tmp_path


def _scores(failed: tuple[str, ...] = ()) -> dict:
    return {
        name: RubricDimensionScore(
            dimension=name, score=1 if name in failed else 8, justification="A justification.",
            evidence_citations=[], evaluation_failed=name in failed,
            failure_class="timeout" if name in failed else None,
        )
        for name in DIMENSIONS
    }


def _save(**overrides):
    kwargs = {
        "experiment_name": "SprintSight Evaluations", "model_name": "sprintsight-qwen", "team_id": "team-a",
        "sprint_id": "s1", "trace_id": "tr-1", "run_id": "run-1", "overall_score": 8.0,
        "scores_by_dim": _scores(), "failed_dimensions": {}, "failure_classes": {},
        "prompt_versions": {"Evaluate_testing": 3}, "duration_seconds": 123.456,
    }
    return save_results.save_run_results(**{**kwargs, **overrides})


def _rows(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_a_row_has_every_unified_column(results_dir) -> None:
    raw_path, _ = _save()

    row = _rows(raw_path)[0]

    assert set(base_record()) <= set(row)
    assert (row["example_id"], row["trace_id"], row["model"], row["latency_s"]) == ("team-a|s1", "tr-1", "sprintsight-qwen", 123.46)
    assert row["format_valid"] is True and row["dimensions_failed"] == 0
    assert row["score_testing"] == 8


def test_a_failed_dimension_is_recorded_as_failed_not_as_a_score_of_one(results_dir) -> None:
    raw_path, _ = _save(
        scores_by_dim=_scores(failed=("testing",)),
        failed_dimensions={"testing": "timeout: ReadTimeout: slow"}, failure_classes={"testing": "timeout"},
    )

    row = _rows(raw_path)[0]

    assert row["score_testing"] is None
    assert row["failed_dimension_names"] == ["testing"]
    assert row["failure_classes"] == {"testing": "timeout"}
    assert row["failure_details"] == {"testing": "timeout: ReadTimeout: slow"}
    assert row["format_valid"] is False
    assert row["rubric_mean"] == 8.0  # mean of the five real scores


def test_artifacts_are_attached_to_the_grading_run_by_id(results_dir) -> None:
    _save()

    assert [(run_id, path) for run_id, path, _ in LOGGED] == [
        ("run-1", "trial_results"), ("run-1", "trial_results"),
    ]


def test_the_summary_reports_failures_by_class(results_dir) -> None:
    _save(trace_id="tr-1")
    _, summary_path = _save(
        trace_id="tr-2", scores_by_dim=_scores(failed=("testing", "cicd")),
        failed_dimensions={"testing": "timeout: x", "cicd": "schema_validation: y"},
        failure_classes={"testing": "timeout", "cicd": "schema_validation"},
    )

    team = json.loads(summary_path.read_text(encoding="utf-8"))["teams"]["team-a"]

    assert team["runs"] == 2 and team["runs_with_failed_dimensions"] == 1
    assert team["failure_classes"] == {"timeout": 1, "schema_validation": 1}
    assert team["trace_ids"] == ["tr-1", "tr-2"]
    assert team["mean_dimension_scores"]["testing"] == 8  # the failed run's placeholder is not averaged in


def test_result_files_written_before_the_unified_schema_still_summarise() -> None:
    old_row = {
        "team_id": "team-a", "sprint_id": "s1", "model": "m", "run_id": "r", "trace_id": "tr-old",
        "overall_score": 6.0, "dimension_scores": dict.fromkeys(DIMENSIONS, 6),
        "failed_dimensions": {}, "prompt_versions": {}, "duration_seconds": 50,
    }

    summary = save_results._summarize_raw_results([old_row], {"experiment": "e"})

    assert summary["teams"]["team-a"]["mean_overall_score"] == 6.0
    assert summary["teams"]["team-a"]["runs_with_failed_dimensions"] == 0


def test_a_failing_artifact_upload_does_not_fail_the_assessment(results_dir, monkeypatch) -> None:
    class Broken:
        def log_artifact(self, *args, **kwargs):
            raise ConnectionError("mlflow down")

    monkeypatch.setattr(save_results.mlflow, "MlflowClient", Broken)

    raw_path, _ = _save()  # must not raise: results are a by-product of grading

    assert raw_path.exists()
