"""Judge status edge cases: late traces, late judges, failure reasons, MLflow error mapping."""

from datetime import UTC, datetime, timedelta

import pytest

from app.repositories.insights import RunRow
from app.services.insightsService import mlflow_gateway as gateway_module
from app.services.insightsService.fake_gateway import FakeMlflowGateway
from app.services.insightsService.judge import (
    derive_judge_status,
    failure_class,
    failure_description,
    judge_values,
)
from app.services.insightsService.mlflow_gateway import (
    MlflowUnavailable,
    RealMlflowGateway,
    TraceNotFound,
)
from app.services.insightsService.service import refresh_judge_status
from app.services.insightsService.trace_summary import (
    JudgeAssessment,
    TraceSummary,
    summarize_trace,
)

NOW = datetime.now(UTC)
STALE = timedelta(minutes=120)


def _summary(*assessments: JudgeAssessment, tags: dict[str, str] | None = None) -> TraceSummary:
    return TraceSummary(trace_id="tr-1", duration_ms=1, assessments=assessments, judge_tags=tags or {})


def _done(name: str, error: str | None = None) -> JudgeAssessment:
    return JudgeAssessment(name=name, value=0.0, source="LLM_JUDGE", error=error)


BOTH = (_done("citation_hallucination_rate"), _done("narrative_contradiction_count"))


class RecordingInsights:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def set_judge_status(self, report_id, status, summary) -> None:
        self.calls.append((report_id, status))


def _run(age: timedelta, *, trace_id="tr-1", status="pending") -> RunRow:
    return RunRow(
        report_id="r1", course_id="c", course_code="C", course_name="C", section="1",
        project_id="p", team_name="t", sprint_id="s", model_name="m",
        generated_at=NOW - age, team_score=70.0, trace_id=trace_id, judge_status=status,
        judge_checked_at=None, judge_summary=None,
    )


# ------------------------------------------------------------------ derive_judge_status
def test_complete_when_both_markers_exist() -> None:
    assert derive_judge_status(_summary(*BOTH), NOW, NOW, STALE) == "complete"


def test_judge_that_runs_longer_than_thirty_minutes_is_still_pending() -> None:
    generated = NOW - timedelta(minutes=45)
    assert derive_judge_status(_summary(), generated, NOW, STALE) == "pending"
    assert derive_judge_status(_summary(), NOW - timedelta(hours=3), NOW, STALE) == "stale"


def test_skipped_and_abandoned_traces_are_failed_not_stale() -> None:
    old = NOW - timedelta(hours=3)
    skipped = _summary(tags={"judge.skipped": "all_dimensions_failed"})
    dead = _summary(tags={"judge.dead": "timeout"})
    assert derive_judge_status(skipped, old, NOW, STALE) == "failed"
    assert derive_judge_status(dead, NOW, NOW, STALE) == "failed"


def test_a_later_successful_rerun_beats_an_old_dead_tag() -> None:
    summary = _summary(*BOTH, tags={"judge.dead": "timeout"})
    assert derive_judge_status(summary, NOW, NOW, STALE) == "complete"


def test_marker_with_an_error_is_failed() -> None:
    summary = _summary(_done("citation_hallucination_rate", error="boom"))
    assert derive_judge_status(summary, NOW, NOW, STALE) == "failed"


# ------------------------------------------------------------------ failure reasons
def test_failure_class_comes_from_assessment_then_tags() -> None:
    recorded = JudgeAssessment(
        name="citation_judge_failure_class", value=None, source="LLM_JUDGE", text="remote_judge_disabled"
    )
    assert failure_class(_summary(recorded)) == "remote_judge_disabled"
    assert failure_class(_summary(tags={"judge.skipped": "x"})) == "skipped_all_dimensions_failed"
    assert failure_class(_summary(tags={"judge.dead": "timeout"})) == "timeout"
    assert failure_class(_summary(tags={"judge.dead": ""})) == "retries_exhausted"
    assert failure_class(_summary()) is None
    assert judge_values(_summary(recorded))["failure_class"] == "remote_judge_disabled"


def test_failure_descriptions_are_fixed_sentences_never_raw_errors() -> None:
    assert "not configured" in failure_description("remote_judge_disabled")
    assert failure_description("something-new") == failure_description("unknown")
    assert failure_description(None) is None


def test_summarize_trace_reads_the_string_failure_class_and_judge_tags() -> None:
    from types import SimpleNamespace

    assessment = SimpleNamespace(
        name="citation_judge_failure_class", value="timeout", valid=True, error=None,
        source=SimpleNamespace(source_type="LLM_JUDGE"), rationale="long internal text", metadata={},
    )
    info = SimpleNamespace(
        trace_id="tr-1", execution_duration=5, assessments=[assessment],
        tags={"judge.dead": "timeout", "mlflow.user": "x", "prompt.A": "3"},
    )
    summary = summarize_trace(SimpleNamespace(data=SimpleNamespace(spans=[]), info=info))

    assert failure_class(summary) == "timeout"
    assert summary.judge_tags == {"judge.dead": "timeout"}  # unrelated tags never leave


# ------------------------------------------------------------------ refresh_judge_status
def test_fresh_report_with_unexported_trace_stays_pending() -> None:
    insights, gateway = RecordingInsights(), FakeMlflowGateway()  # the gateway has no such trace
    status = refresh_judge_status(_run(timedelta(minutes=2)), gateway, insights, stale_minutes=120)
    assert status == "pending"
    assert insights.calls == [("r1", "pending")]


def test_old_report_with_missing_trace_becomes_no_trace() -> None:
    insights, gateway = RecordingInsights(), FakeMlflowGateway()
    status = refresh_judge_status(_run(timedelta(hours=5)), gateway, insights, stale_minutes=120)
    assert status == "no_trace"


def test_stale_report_recovers_when_the_judge_finally_finishes() -> None:
    insights, gateway = RecordingInsights(), FakeMlflowGateway()
    gateway.traces["tr-1"] = _summary(*BOTH)
    status = refresh_judge_status(
        _run(timedelta(hours=1), status="stale"), gateway, insights, stale_minutes=120
    )
    assert status == "complete"


def test_mlflow_outage_is_not_recorded_as_a_status() -> None:
    insights, gateway = RecordingInsights(), FakeMlflowGateway()
    gateway.down = True
    with pytest.raises(MlflowUnavailable):
        refresh_judge_status(_run(timedelta(hours=5)), gateway, insights, stale_minutes=120)
    assert insights.calls == []


# ------------------------------------------------------------------ RealMlflowGateway
class _FakeClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_trace(self, trace_id, display=False):
        raise self.error


def _real_gateway(error: Exception) -> RealMlflowGateway:
    gateway = RealMlflowGateway("http://mlflow.invalid:5000")
    gateway._mlflow = lambda: (None, _FakeClient(error))  # type: ignore[method-assign]
    return gateway


class _CodedError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = code


def test_only_mlflows_missing_trace_code_means_trace_not_found() -> None:
    missing = _real_gateway(_CodedError("RESOURCE_DOES_NOT_EXIST", "Trace with ID 'x' not found."))
    with pytest.raises(TraceNotFound):
        missing.get_trace_summary("tr-1")


@pytest.mark.parametrize(
    "error",
    [
        _CodedError("ENDPOINT_NOT_FOUND", "404 page not found (version mismatch)"),
        RuntimeError("server not found"),
        _CodedError("INTERNAL_ERROR", "API request failed"),
    ],
)
def test_other_errors_are_an_outage_never_a_missing_trace(error) -> None:
    with pytest.raises(MlflowUnavailable):
        _real_gateway(error).get_trace_summary("tr-1")


def test_trace_cache_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(gateway_module, "MAX_CACHED_TRACES", 3)
    monkeypatch.setattr(gateway_module, "summarize_trace", lambda trace: _summary())
    gateway = RealMlflowGateway("http://mlflow.invalid:5000")
    gateway._mlflow = lambda: (None, type("C", (), {"get_trace": lambda self, t, display=False: t})())  # type: ignore[method-assign]
    for index in range(10):
        gateway.get_trace_summary(f"tr-{index}")
    assert len(gateway._cache) == 3
