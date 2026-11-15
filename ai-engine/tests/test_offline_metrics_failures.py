"""Failure classes reach per_example rows, including when every dimension failed."""

import asyncio

import pytest

from evaluation.offline.datasets import DatasetItem
from evaluation.offline import metrics, runner
from evaluation.offline.metrics import summarise_example
from prompts.dimension_criteria import DIMENSIONS
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment

BUNDLE = ArtifactBundle(team_id="t", sprint_id="s1")


@pytest.fixture(autouse=True)
def no_grounding(monkeypatch):
    monkeypatch.setattr(metrics, "_bundle_corpus", lambda bundle: "")
    monkeypatch.setattr(metrics, "find_ungrounded_citations", lambda corpus, citations: [])


def _assessment(failed: dict[str, tuple[str, str]] | None = None) -> SprintAssessment:
    """Every dimension scored, except `failed` = {dimension: (failure_class, error_detail)}."""
    failed = failed or {}
    dims = {}
    for name in DIMENSIONS:
        if name in failed:
            failure_class, detail = failed[name]
            dims[name] = RubricDimensionScore(
                dimension=name, score=1, justification="Could not be scored.",
                evaluation_failed=True, failure_class=failure_class, error_detail=detail,
            )
        else:
            dims[name] = RubricDimensionScore(dimension=name, score=7, justification="A justification.")
    return SprintAssessment(
        sprint_id="s1", team_id="t", overall_score=7, rubric_scores=RubricsScore(**dims),
        executive_summary="Summary.", key_recommendations=["Do it."], trace_id="tr-1",
    )


def test_one_failed_dimension_is_recorded_with_class_and_detail() -> None:
    first = DIMENSIONS[0]

    row = summarise_example(BUNDLE, _assessment({first: ("timeout", "ReadTimeout: 120s")}), None)

    assert row["failure_classes"] == {first: "timeout"}
    assert row["failure_details"] == {first: "ReadTimeout: 120s"}
    assert row["failed_dimension_names"] == [first]


def test_a_clean_assessment_leaves_the_failure_columns_empty() -> None:
    row = summarise_example(BUNDLE, _assessment(), None)

    assert row["failure_classes"] == {}
    assert row["failure_details"] == {}


def test_all_dimensions_failed_keeps_the_classes_from_the_exception(monkeypatch) -> None:
    failed = {
        dim: "timeout: ReadTimeout: 120s" if i == 0 else f"schema_validation: bad json in {dim}"
        for i, dim in enumerate(DIMENSIONS)
    }

    async def all_fail(*args, **kwargs):
        raise AllDimensionsFailedError(failed)

    monkeypatch.setattr(runner, "evaluate_sprint", all_fail)
    item = DatasetItem(id="ex1", bundle=BUNDLE)

    row, raw, error = asyncio.run(runner._run_one_example(item, "fake-model", "exp"))

    assert raw is None
    assert error and error.startswith("AllDimensionsFailedError")
    assert row["failure_classes"] == {
        dim: "timeout" if i == 0 else "schema_validation" for i, dim in enumerate(DIMENSIONS)
    }
    assert row["failure_details"][DIMENSIONS[0]] == "ReadTimeout: 120s"
    assert row["failure_details"][DIMENSIONS[1]] == f"bad json in {DIMENSIONS[1]}"
    assert row["format_valid"] is False


def test_failure_text_without_a_class_keeps_its_detail_only() -> None:
    classes, details = runner._failures_from_error(AllDimensionsFailedError({"cicd": "boom"}))

    assert classes == {}
    assert details == {"cicd": "boom"}
