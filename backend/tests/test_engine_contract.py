"""What the backend assumes about the engine's response, checked against a golden document the
engine's own tests (ai-engine/tests/test_backend_contract.py) also validate."""

import json
import threading
from pathlib import Path

import httpx
import pytest

from app.api.v1.endpoints.assessment import build_assessment_executor
from app.core.config import get_settings
from app.services.assessmentService.service import convert_ai_result_to_assessment_report
from app.services.insightsService.trace_summary import AI_ENGINE_DIMENSION_ORDER, collect_claims
from app.services.middleManService.service import AIEngineError, send_assessment_to_ai_engine

GOLDEN = Path(__file__).parent / "fixtures" / "engine_sprint_assessment.json"
PAYLOAD = {"course_id": "c", "project_id": "p", "sprint_id": "sprint-1", "model_name": "m"}


def _engine_response() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_dimension_order_matches_the_engine() -> None:
    assert list(AI_ENGINE_DIMENSION_ORDER) == _engine_response()["contract_dimension_order"]


def test_engine_response_converts_to_a_report_without_the_failed_dimension() -> None:
    report = convert_ai_result_to_assessment_report(PAYLOAD, _engine_response())

    assert report.trace_id == "tr-golden"
    assert report.failed_dimensions == ["cicd"]
    assert report.evaluation_failed is True
    assert set(report.rubric_scores) == set(AI_ENGINE_DIMENSION_ORDER)
    assert report.rubric_scores["cicd"].evaluation_failed is True
    assert report.rubric_scores["cicd"].failure_class == "timeout"
    # team score averages only the five assessed dimensions (7 each) and renormalises
    assert report.team_score.score == 70.0
    assert report.ai_rubric_scores_original == {
        name: 7.0 for name in AI_ENGINE_DIMENSION_ORDER if name != "cicd"
    }
    assert report.rubric_scores["code_quality"].evidence_details[0].identifier == "src/app.py:L10-L24@abc1234"


def test_judge_claim_numbering_follows_the_engines_order_and_skips_failed_dimensions() -> None:
    outputs = {"rubric_scores": _engine_response()["rubric_scores"]}

    claims = collect_claims(outputs)

    # 5 assessed dimensions x 2 citations; the failed one (cicd) is skipped, as in the judge
    assert list(claims) == [f"C{n}" for n in range(1, 11)]
    assert claims["C1"].startswith("src/app.py:L10-L24@abc1234 | code_quality")
    assert claims["C3"].startswith("src/app.py:L10-L24@abc1234 | testing")


def _engine_replies(monkeypatch, response: httpx.Response) -> None:
    response.request = httpx.Request("POST", "http://engine/assess/sprint/data")
    monkeypatch.setattr(
        "app.services.middleManService.service.httpx.post", lambda *args, **kwargs: response
    )


def _failed_call(monkeypatch, response: httpx.Response) -> AIEngineError:
    _engine_replies(monkeypatch, response)
    with pytest.raises(AIEngineError) as raised:
        send_assessment_to_ai_engine({}, "m")
    return raised.value


def _engine_failure(failure_class: str) -> httpx.Response:
    """What ai-engine/api/assessment.py sends when an assessment fails."""
    detail = {"error": "assessment_failed", "failure_class": failure_class, "message": "..."}
    return httpx.Response(500, json={"detail": detail})


@pytest.mark.parametrize(
    ("failure_class", "transient"),
    [
        ("timeout", True),
        ("infra_unavailable", True),
        ("schema_validation", False),
        ("output_length", False),
        ("context_truncated", False),
        ("unknown", False),
    ],
)
def test_the_engines_failure_class_decides_whether_a_500_is_worth_retrying(
    monkeypatch, failure_class: str, transient: bool
) -> None:
    error = _failed_call(monkeypatch, _engine_failure(failure_class))

    assert error.transient is transient
    assert error.failure_class == failure_class
    assert error.kind == "engine_error"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(500, json={"detail": "assessment failed"}),
        httpx.Response(500, json=["not", "an", "object"]),
        httpx.Response(500, json={"detail": {"failure_class": 7}}),
    ],
)
def test_a_500_without_a_usable_failure_class_is_not_retried(monkeypatch, response) -> None:
    error = _failed_call(monkeypatch, response)

    assert error.transient is False
    assert error.failure_class is None


def test_gateway_status_codes_are_still_transient_without_a_failure_class(monkeypatch) -> None:
    for status_code in (502, 503, 504):
        assert _failed_call(monkeypatch, httpx.Response(status_code, text="bad gateway")).transient


def _two_jobs_overlap(executor) -> bool:
    """Submit a job that holds its worker, then a second; True if the second starts meanwhile."""
    first_running, release_first, second_started = (threading.Event() for _ in range(3))
    try:
        executor.submit(lambda: (first_running.set(), release_first.wait(10)))
        assert first_running.wait(5)
        executor.submit(second_started.set)
        return second_started.wait(0.5)
    finally:
        release_first.set()
        executor.shutdown(wait=True)


def test_one_job_at_a_time_reaches_the_engine_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AI_ENGINE_MAX_CONCURRENCY", raising=False)
    get_settings.cache_clear()

    assert get_settings().ai_engine_max_concurrency == 1
    assert _two_jobs_overlap(build_assessment_executor()) is False


def test_the_engine_concurrency_can_be_raised_but_never_below_one(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENGINE_MAX_CONCURRENCY", "2")
    get_settings.cache_clear()
    assert _two_jobs_overlap(build_assessment_executor()) is True

    monkeypatch.setenv("AI_ENGINE_MAX_CONCURRENCY", "0")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
