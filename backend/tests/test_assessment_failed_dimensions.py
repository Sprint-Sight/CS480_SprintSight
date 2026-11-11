"""A dimension the AI engine could not score must never silently become a score.

The engine ships a placeholder (score 1, evaluation_failed true) for a dimension whose
retries were exhausted. These tests pin down that the backend excludes it from the team
score, flags the report for manual review, keeps the trace id for the judge join, and
bounds/classifies the call to the engine.
"""

from types import SimpleNamespace

import httpx
import pytest

from app.schemas.assessment import AssessmentReport
from app.services.assessmentService.service import (
    RUBRIC_WEIGHTS,
    convert_ai_result_to_assessment_report,
)
from app.services.middleManService.service import (
    DEFAULT_AI_ENGINE_READ_TIMEOUT_SECONDS,
    AIEngineError,
    send_assessment_to_ai_engine,
)

DIMENSIONS = list(RUBRIC_WEIGHTS)
PAYLOAD = {"course_id": "c", "project_id": "p", "sprint_id": "s1", "model_name": "m"}


def _dimension(name: str, score: int, **extra) -> dict:
    return {
        "dimension": name,
        "score": score,
        "justification": f"{name} justification.",
        "evidence_citations": [],
        **extra,
    }


def _failed(name: str, failure_class: str = "timeout") -> dict:
    return _dimension(
        name,
        1,
        justification="Automated evaluation failed for this dimension. Manual review required.",
        evaluation_failed=True,
        failure_class=failure_class,
    )


def _ai_result(scores: dict[str, int], failed: tuple[str, ...] = (), **extra) -> dict:
    rubric = {name: _dimension(name, score) for name, score in scores.items()}
    for name in failed:
        rubric[name] = _failed(name)
    return {
        "overall_score": 8,
        "executive_summary": "Engine summary.",
        "key_recommendations": ["Add tests."],
        "rubric_scores": rubric,
        **extra,
    }


def _all(score: int) -> dict[str, int]:
    return dict.fromkeys(DIMENSIONS, score)


# ---------------------------------------------------------------- score calculation


def test_failed_dimension_is_excluded_from_team_score() -> None:
    scores = _all(8)
    del scores["testing"]
    result = _ai_result(scores, failed=("testing",), failed_dimensions=["testing"])

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    # Five dimensions at 8 -> 80. Counting the placeholder 1 would give (5*8+1)/6*10 = 68.33.
    assert report.team_score.score == 80.0
    assert report.evaluation_failed is True
    assert report.failed_dimensions == ["testing"]


def test_failed_dimension_keeps_its_flag_but_not_a_real_score_meaning() -> None:
    scores = _all(8)
    del scores["cicd"]
    report = convert_ai_result_to_assessment_report(
        PAYLOAD, _ai_result(scores, failed=("cicd",), failed_dimensions=["cicd"])
    )

    detail = report.rubric_scores["cicd"]
    assert detail.evaluation_failed is True
    assert detail.failure_class == "timeout"
    assert report.rubric_scores["testing"].evaluation_failed is False


def test_team_rationale_names_the_dimensions_pending_manual_review() -> None:
    scores = _all(7)
    for name in ("testing", "cicd"):
        del scores[name]
    result = _ai_result(scores, failed=("testing", "cicd"), failed_dimensions=["cicd", "testing"])

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    assert report.failed_dimensions == ["testing", "cicd"]  # rubric order, not engine order
    assert "manual review" in report.team_score.rationale
    assert "testing, cicd" in report.team_score.rationale
    assert report.team_score.rationale.endswith("Engine summary.")


def test_failure_is_detected_from_the_per_dimension_flag_alone() -> None:
    # An engine that predates the top-level failed_dimensions list still gets handled.
    scores = _all(9)
    del scores["requirements"]
    result = _ai_result(scores, failed=("requirements",))
    assert "failed_dimensions" not in result

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    assert report.failed_dimensions == ["requirements"]
    assert report.team_score.score == 90.0


def test_custom_weights_are_renormalised_over_the_assessed_dimensions() -> None:
    weights = {name: 0.0 for name in DIMENSIONS}
    weights.update({"code_quality": 0.6, "testing": 0.2, "documentation": 0.2})
    scores = {"code_quality": 10, "documentation": 5}
    result = _ai_result(scores, failed=("testing",), failed_dimensions=["testing"])

    report = convert_ai_result_to_assessment_report(PAYLOAD, result, rubric_weights=weights)

    # (10 * 0.6 + 5 * 0.2) / (0.6 + 0.2) = 8.75 -> 87.5
    assert report.team_score.score == 87.5


def test_every_dimension_failing_scores_zero_and_is_flagged() -> None:
    result = _ai_result({}, failed=tuple(DIMENSIONS), failed_dimensions=DIMENSIONS)

    report = convert_ai_result_to_assessment_report(PAYLOAD, result)

    assert report.team_score.score == 0.0
    assert report.evaluation_failed is True
    assert report.failed_dimensions == DIMENSIONS


def test_clean_result_is_unchanged_and_unflagged() -> None:
    report = convert_ai_result_to_assessment_report(PAYLOAD, _ai_result(_all(8), trace_id="tr-abc"))

    assert report.team_score.score == 80.0
    assert report.evaluation_failed is False
    assert report.failed_dimensions == []
    assert report.team_score.rationale == "Engine summary."


def test_trace_id_is_carried_onto_the_report() -> None:
    with_trace = convert_ai_result_to_assessment_report(
        PAYLOAD, _ai_result(_all(8), trace_id="tr-123")
    )
    without_trace = convert_ai_result_to_assessment_report(PAYLOAD, _ai_result(_all(8)))

    assert with_trace.trace_id == "tr-123"
    assert without_trace.trace_id is None


def test_old_rows_without_the_new_fields_still_validate() -> None:
    report = convert_ai_result_to_assessment_report(PAYLOAD, _ai_result(_all(8)))
    legacy = report.model_dump(
        mode="json", exclude={"trace_id", "evaluation_failed", "failed_dimensions"}
    )

    restored = AssessmentReport.model_validate(legacy)

    assert restored.trace_id is None
    assert restored.evaluation_failed is False
    assert restored.failed_dimensions == []


# ------------------------------------------------------------- engine transport


def _settings(**overrides):
    base = {"ai_engine_url": "http://engine:8001/", "default_model_name": "m"}
    return SimpleNamespace(**{**base, **overrides})


def _patch_post(monkeypatch, *, response=None, error=None, settings=None):
    seen: dict = {}

    def fake_post(url, json=None, timeout=None):
        seen["timeout"] = timeout
        if error is not None:
            raise error
        return response

    monkeypatch.setattr("app.services.middleManService.service.httpx.post", fake_post)
    monkeypatch.setattr(
        "app.services.middleManService.service.get_settings", lambda: settings or _settings()
    )
    return seen


def _response(status: int, body: str = "") -> httpx.Response:
    return httpx.Response(status, text=body, request=httpx.Request("POST", "http://engine"))


def test_engine_call_has_a_finite_read_timeout_by_default(monkeypatch) -> None:
    seen = _patch_post(monkeypatch, response=_response(200, "{}"))

    send_assessment_to_ai_engine({"x": 1}, "m")

    assert isinstance(seen["timeout"], httpx.Timeout)
    assert seen["timeout"].read == DEFAULT_AI_ENGINE_READ_TIMEOUT_SECONDS
    assert seen["timeout"].connect is not None and seen["timeout"].connect <= 30


def test_engine_call_honours_the_configured_timeout(monkeypatch) -> None:
    seen = _patch_post(
        monkeypatch,
        response=_response(200, "{}"),
        settings=_settings(ai_engine_timeout_seconds=45),
    )

    send_assessment_to_ai_engine({"x": 1}, "m")

    assert seen["timeout"].read == 45


@pytest.mark.parametrize("configured", [0, -5, None, "nonsense"])
def test_a_missing_or_invalid_timeout_never_means_unbounded(monkeypatch, configured) -> None:
    seen = _patch_post(
        monkeypatch,
        response=_response(200, "{}"),
        settings=_settings(ai_engine_timeout_seconds=configured),
    )

    send_assessment_to_ai_engine({"x": 1}, "m")

    assert seen["timeout"].read == DEFAULT_AI_ENGINE_READ_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    ("error", "response", "kind", "transient"),
    [
        (httpx.ReadTimeout("slow"), None, "timeout", True),
        (httpx.ConnectError("refused"), None, "unavailable", True),
        (None, _response(503, "overloaded"), "engine_error", True),
        (None, _response(500, "all dimensions failed"), "engine_error", False),
        (None, _response(422, "bad payload"), "rejected", False),
        (None, _response(200, "<html>not json</html>"), "invalid_response", False),
    ],
)
def test_engine_failures_are_classified(monkeypatch, error, response, kind, transient) -> None:
    _patch_post(monkeypatch, error=error, response=response)

    with pytest.raises(AIEngineError) as raised:
        send_assessment_to_ai_engine({"x": 1}, "m")

    assert raised.value.kind == kind
    assert raised.value.transient is transient
