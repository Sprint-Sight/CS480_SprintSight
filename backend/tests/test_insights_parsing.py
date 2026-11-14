from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.insightsService.citations import parse_citation_rationale
from app.services.insightsService.judge import derive_judge_status
from app.services.insightsService.trace_summary import (
    JudgeAssessment,
    TraceSummary,
    collect_claims,
    summarize_trace,
)


def test_parses_real_rationale_format_with_continuation_and_claims():
    text = ("C7 [documentation] partially_grounded/minor_detail: Commit message is generic.\n"
            "C8 [documentation] hallucinated/major_misattribution: README.md does not\n"
            "exist at that commit.")
    rows, truncated = parse_citation_rationale(text, {"C8": "README.md | Added docs"})
    assert [r.citation_id for r in rows] == ["C7", "C8"]
    assert rows[1].verdict == "hallucinated" and rows[1].severity == "major_misattribution"
    assert rows[1].reasoning.endswith("exist at that commit.")
    assert rows[1].claim == "README.md | Added docs" and rows[0].claim is None
    assert truncated is False


def test_marks_truncated_rationale_and_ignores_all_grounded_message():
    rows, truncated = parse_citation_rationale("C1 [testing] hallucinated/major_misattribution: x" * 60, {})
    assert truncated is True
    assert parse_citation_rationale("every judged citation was grounded", {}) == ([], False)


def test_claim_numbering_matches_ai_engine_order_and_skips_failed_dimensions():
    outputs = {"rubric_scores": {
        "testing": {"evidence_citations": [{"identifier": "t1", "reason": "tests"}]},
        "code_quality": {"evidence_citations": [{"identifier": "c1", "reason": "clean"}]},
        "documentation": {"evaluation_failed": True, "evidence_citations": [{"identifier": "d", "reason": "x"}]},
        "requirements": {"evidence_citations": [{"identifier": "r1", "reason": "done"}]},
    }}
    assert collect_claims(outputs) == {"C1": "c1 | clean", "C2": "t1 | tests", "C3": "r1 | done"}


def test_judge_status_rules():
    now = datetime.now(UTC)
    done = TraceSummary("t", 1, assessments=(JudgeAssessment("citation_hallucination_rate", 0.1, "LLM_JUDGE"),
                                             JudgeAssessment("narrative_contradiction_count", 0.0, "LLM_JUDGE")))
    failed = TraceSummary("t", 1, assessments=(JudgeAssessment("citation_hallucination_rate", None, "LLM_JUDGE",
                                                               error="boom"),))
    empty = TraceSummary("t", 1)
    stale = timedelta(minutes=30)
    assert derive_judge_status(done, now, now, stale) == "complete"
    assert derive_judge_status(failed, now, now, stale) == "failed"
    assert derive_judge_status(empty, now, now, stale) == "pending"
    assert derive_judge_status(empty, now - timedelta(hours=1), now, stale) == "stale"


def _span(span_id, name, parent, start_ms, end_ms, outputs=None, attrs=None):
    return SimpleNamespace(span_id=span_id, name=name, parent_id=parent, start_time_ns=start_ms * 1_000_000,
                           end_time_ns=end_ms * 1_000_000, status=SimpleNamespace(status_code="OK"),
                           outputs=outputs, inputs={"bundle": "STUDENT CODE"},
                           get_attribute=lambda key, attrs=attrs: (attrs or {}).get(key))


def test_summarize_trace_strips_payloads_and_collapses_llm_calls():
    root = _span("r", "Evaluate_Complete_Sprint", None, 0, 9000,
                 outputs={"rubric_scores": {"testing": {"evidence_citations": [{"identifier": "a", "reason": "b"}]}}},
                 attrs={"prompt_versions": {"sprint_feedback_prompt": "2"}})
    trace = SimpleNamespace(
        data=SimpleNamespace(spans=[root, _span("d", "Evaluate_Dimension_testing", "r", 100, 4000),
                                    _span("l", "AsyncCompletions", "d", 200, 3900)]),
        info=SimpleNamespace(trace_id="tr-1", execution_duration=9000,
                             tags={"prompt.Evaluate_testing": "3", "team_id": "x"},
                             assessments=[
                                 SimpleNamespace(name="gold", value={"secret": 1}, source=None, metadata={}),
                                 SimpleNamespace(name="citation_grounded_rate", value=0.8, rationale=None,
                                                 error=None, metadata={}, valid=True,
                                                 source=SimpleNamespace(source_type="LLM_JUDGE")),
                             ]),
    )
    summary = summarize_trace(trace)
    assert [s.name for s in summary.spans] == ["Evaluate_Complete_Sprint", "Evaluate_Dimension_testing"]
    assert summary.llm_call_count == 1
    assert [a.name for a in summary.assessments] == ["citation_grounded_rate"]  # 'gold' filtered out
    assert summary.prompt_versions == {"Evaluate_testing": "3", "Generate_Sprint_Feedback": "2"}
    assert summary.claims == {"C1": "a | b"}
    assert "STUDENT CODE" not in repr(summary)
