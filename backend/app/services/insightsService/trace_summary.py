"""Reduce an MLflow Trace to the small, safe shape SprintSight shows.

Safety rule: span inputs/outputs never leave this module, except the evidence-citation
claims ("identifier | reason") the AI already put in the report. No prompts, no student
code, no raw model responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HIDDEN_SPANS = frozenset({"AsyncCompletions"})  # raw LLM calls: counted, never shown
# Must match DIMENSIONS in ai-engine prompts/dimension_criteria.py: the judge numbers its
# citations C1..Cn in this order (evaluation/judges/citation_grounding.py collect_citations).
AI_ENGINE_DIMENSION_ORDER = (
    "code_quality",
    "testing",
    "documentation",
    "requirements",
    "collaboration",
    "cicd",
)
ALLOWED_ASSESSMENTS = frozenset(
    {
        "citation_hallucination_rate",
        "citation_grounded_rate",
        "citation_count",
        "judge_coverage",
        "citation_severity_weighted_rate",
        "citation_severity_weighted_rate_incl_dropped",
        "citations_dropped_by_code",
        "citation_prefilter_drop_rate",
        "justification_hard_contradictions",
        "narrative_contradiction_count",
        "narrative_contradiction_rate",
        "narrative_item_count",
    }
)

@dataclass(frozen=True)
class SpanTiming:
    name: str
    parent: str | None
    start_offset_ms: int
    duration_ms: int
    status: str

@dataclass(frozen=True)
class JudgeAssessment:
    name: str
    value: float | None
    source: str
    rationale: str | None = None
    error: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class TraceSummary:
    trace_id: str
    duration_ms: int
    spans: tuple[SpanTiming, ...] = ()
    llm_call_count: int = 0
    assessments: tuple[JudgeAssessment, ...] = ()
    prompt_versions: dict[str, str] = field(default_factory=dict)
    claims: dict[str, str] = field(default_factory=dict)  # "C3" -> "identifier | reason"

    def assessment(self, name: str) -> JudgeAssessment | None:
        return next((a for a in self.assessments if a.name == name), None)

def summarize_trace(trace: Any) -> TraceSummary:
    spans = list(getattr(trace.data, "spans", None) or [])
    by_id = {s.span_id: s for s in spans}
    root = next((s for s in spans if s.parent_id is None), None)
    origin = root.start_time_ns if root else min((s.start_time_ns for s in spans), default=0)

    timings: list[SpanTiming] = []
    llm_calls = 0
    for span in sorted(spans, key=lambda s: s.start_time_ns):
        if span.name in HIDDEN_SPANS:
            llm_calls += 1
            continue
        end = span.end_time_ns or span.start_time_ns
        parent = by_id.get(span.parent_id) if span.parent_id else None
        timings.append(
            SpanTiming(
                name=span.name,
                parent=parent.name if parent else None,
                start_offset_ms=max(0, (span.start_time_ns - origin) // 1_000_000),
                duration_ms=max(0, (end - span.start_time_ns) // 1_000_000),
                status=_status(span),
            )
        )

    info = trace.info
    duration = getattr(info, "execution_duration", None)
    if duration is None and root is not None:
        duration = ((root.end_time_ns or root.start_time_ns) - root.start_time_ns) // 1_000_000

    return TraceSummary(
        trace_id=info.trace_id,
        duration_ms=int(duration or 0),
        spans=tuple(timings),
        llm_call_count=llm_calls,
        assessments=tuple(_assessments(getattr(info, "assessments", None) or [])),
        prompt_versions=_prompt_versions(getattr(info, "tags", None) or {}, root),
        claims=collect_claims(root.outputs if root is not None else None),
    )

def collect_claims(outputs: Any) -> dict[str, str]:
    """Rebuild the judge's C1..Cn numbering from the grading trace's root span output."""
    rubric = outputs.get("rubric_scores") if isinstance(outputs, dict) else None
    if not isinstance(rubric, dict):
        return {}
    claims: dict[str, str] = {}
    n = 0
    for dimension in AI_ENGINE_DIMENSION_ORDER:
        detail = rubric.get(dimension)
        if not isinstance(detail, dict) or detail.get("evaluation_failed"):
            continue
        for citation in detail.get("evidence_citations") or []:
            n += 1
            claims[f"C{n}"] = (
                f"{citation.get('identifier', '')} | {citation.get('reason', '')}"
                if isinstance(citation, dict)
                else str(citation)
            )
    return claims

def _status(span: Any) -> str:
    code = getattr(getattr(span, "status", None), "status_code", None)
    return str(getattr(code, "value", code) or "UNSET")

def _prompt_versions(tags: dict, root: Any) -> dict[str, str]:
    versions = {
        key.removeprefix("prompt."): str(value)
        for key, value in tags.items()
        if key.startswith("prompt.")
    }
    attrs = (
        root.get_attribute("prompt_versions")
        if root is not None and hasattr(root, "get_attribute")
        else None
    )
    if isinstance(attrs, dict) and attrs.get("sprint_feedback_prompt"):
        versions["Generate_Sprint_Feedback"] = str(attrs["sprint_feedback_prompt"])
    return dict(sorted(versions.items()))

def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None

def _assessments(raw: list) -> list[JudgeAssessment]:
    out: list[JudgeAssessment] = []
    for a in raw:
        if a.name not in ALLOWED_ASSESSMENTS or getattr(a, "valid", True) is False:
            continue
        error = getattr(a, "error", None)
        source_type = getattr(getattr(a, "source", None), "source_type", None)
        out.append(
            JudgeAssessment(
                name=a.name,
                value=_number(getattr(a, "value", None)),
                source=str(getattr(source_type, "value", source_type) or ""),
                rationale=getattr(a, "rationale", None),
                error=(getattr(error, "error_message", None) or str(error)) if error else None,
                metadata=dict(getattr(a, "metadata", None) or {}),
            )
        )
    return out