import json

from app.services.insightsService.citations import (
    METADATA_KEY, TRUNCATED_KEY, unaccepted_citations,
)
from app.services.insightsService.trace_summary import JudgeAssessment, TraceSummary

ROW = {"citation_id": "C1", "dimension": "testing", "claim": "abc123 | Added tests",
       "label": "hallucinated", "severity": "major_misattribution", "reasoning": "not in bundle"}

def summary(metadata=None, rationale=None):
    return TraceSummary(
        trace_id="tr", duration_ms=1, llm_call_count=0, spans=(), prompt_versions={},
        claims={"C1": "parsed claim"},
        assessments=(JudgeAssessment("citation_hallucination_rate", 0.5, "LLM_JUDGE",
                                     rationale=rationale, metadata=metadata or {}),),
    )

def test_metadata_gives_claims_and_no_truncation_footer():
    meta = {METADATA_KEY: json.dumps([ROW, {**ROW, "citation_id": "C2", "label": "grounded"}]),
            TRUNCATED_KEY: "false"}
    rows, truncated = unaccepted_citations(summary(meta))
    assert [(r.citation_id, r.claim) for r in rows] == [("C1", "abc123 | Added tests")]
    assert truncated is False

def test_truncation_flag_passes_through():
    _, truncated = unaccepted_citations(
        summary({METADATA_KEY: json.dumps([ROW]), TRUNCATED_KEY: "true"}))
    assert truncated is True

def test_old_traces_fall_back_to_the_rationale_parser():
    rows, _ = unaccepted_citations(
        summary(rationale="C1 [testing] hallucinated/major_misattribution: x"))
    assert [(r.citation_id, r.claim) for r in rows] == [("C1", "parsed claim")]