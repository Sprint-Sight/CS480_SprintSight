"""groundedness_rate must count citations the engine dropped as fabricated."""

import pytest

from evaluation.offline import metrics
from evaluation.offline.metrics import (
    citations_dropped,
    groundedness_rate,
    summarise_example,
)
from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import (
    ResolvedEvidenceCitation,
    RubricDimensionScore,
)
from schemas.rubrics_score import RubricsScore
from schemas.run_record import base_record
from schemas.sprint_assessment import SprintAssessment


@pytest.fixture(autouse=True)
def fake_grounding(monkeypatch):
    # A citation whose identifier contains FAKE is not in the evidence; nothing else needs a bundle.
    monkeypatch.setattr(metrics, "_bundle_corpus", lambda bundle: "")
    monkeypatch.setattr(
        metrics, "find_ungrounded_citations",
        lambda corpus, citations: [c for c in citations if "FAKE" in c.identifier],
    )


def _assessment(surviving: dict[str, list[str]] | None = None, dropped: dict[str, int] | None = None) -> SprintAssessment:
    surviving, dropped = surviving or {}, dropped or {}
    dims = {}
    for name in DIMENSIONS:
        citations = [ResolvedEvidenceCitation(identifier=i, reason="Because of this evidence.") for i in surviving.get(name, [])]
        dims[name] = RubricDimensionScore(
            dimension=name, score=7, justification="A justification.", evidence_citations=citations,
            citations_dropped=dropped.get(name, 0),
        )
    return SprintAssessment(
        sprint_id="s1", team_id="t", overall_score=7, rubric_scores=RubricsScore(**dims),
        executive_summary="Summary.", key_recommendations=["Do it."], trace_id="tr-1",
    )


BUNDLE = ArtifactBundle(team_id="t", sprint_id="s1")


def test_all_surviving_citations_grounded_and_none_dropped() -> None:
    rate, grounded, total = groundedness_rate(BUNDLE, _assessment({"testing": ["a", "b"], "cicd": ["c"]}))
    assert (rate, grounded, total) == (1.0, 3, 3)


def test_dropped_citations_lower_the_rate() -> None:
    # Eight kept and grounded, two removed as fabricated: the old code reported 1.0 for this.
    assessment = _assessment({"testing": list("abcd"), "cicd": list("efgh")}, dropped={"testing": 1, "cicd": 1})

    rate, grounded, total = groundedness_rate(BUNDLE, assessment)

    assert (grounded, total) == (8, 10)
    assert rate == 0.8


def test_an_assessment_whose_every_citation_was_dropped_scores_zero_not_one() -> None:
    rate, grounded, total = groundedness_rate(BUNDLE, _assessment(dropped={"testing": 3}))
    assert (rate, grounded, total) == (0.0, 0, 3)


def test_surviving_but_ungrounded_citations_still_count_against_it() -> None:
    assessment = _assessment({"testing": ["a", "FAKE-1"]}, dropped={"cicd": 2})

    rate, grounded, total = groundedness_rate(BUNDLE, assessment)

    assert (grounded, total) == (1, 4)
    assert rate == 0.25


def test_no_citations_at_all_is_one_with_a_zero_total() -> None:
    assert groundedness_rate(BUNDLE, _assessment()) == (1.0, 0, 0)  # "nothing to check", total says so


def test_citations_dropped_sums_over_dimensions() -> None:
    assert citations_dropped(_assessment(dropped={"testing": 2, "cicd": 1, "documentation": 4})) == 7


def test_the_example_row_reports_drops_and_the_join_keys() -> None:
    row = summarise_example(BUNDLE, _assessment({"testing": ["a"]}, dropped={"testing": 1}), None)

    assert row["citations_dropped"] == 1
    assert row["groundedness_rate"] == 0.5
    assert (row["trace_id"], row["team_id"], row["sprint_id"]) == ("tr-1", "t", "s1")
    assert row["format_valid"] is True


def test_the_example_row_for_a_run_that_produced_nothing_still_has_every_column() -> None:
    row = summarise_example(BUNDLE, None, "AllDimensionsFailedError: boom")

    assert set(base_record()) <= set(row)
    assert row["error"] == "AllDimensionsFailedError: boom"
    assert row["format_valid"] is False and row["groundedness_rate"] is None
