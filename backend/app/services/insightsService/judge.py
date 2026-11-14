"""Judge status and the six reveal tiles, derived from a TraceSummary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.insightsService.trace_summary import TraceSummary

# The judge is "done" when both scorers have written their headline assessment.
DONE_MARKERS = ("citation_hallucination_rate", "narrative_contradiction_count")
SUMMARY_FIELDS = {
    "grounded_rate": "citation_grounded_rate",
    "hallucination_rate": "citation_hallucination_rate",
    "severity_weighted_rate": "citation_severity_weighted_rate",
    "dropped_by_code": "citations_dropped_by_code",
    "justification_contradictions": "justification_hard_contradictions",
    "narrative_contradictions": "narrative_contradiction_count",
    "coverage": "judge_coverage",
    "citation_count": "citation_count",
}

def judge_values(summary: TraceSummary) -> dict:
    values: dict = {}
    for key, name in SUMMARY_FIELDS.items():
        assessment = summary.assessment(name)
        values[key] = assessment.value if assessment else None
    values["trace_duration_ms"] = summary.duration_ms
    return values

def derive_judge_status(
    summary: TraceSummary, generated_at: datetime, now: datetime, stale_after: timedelta
) -> str:
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    markers = [summary.assessment(name) for name in DONE_MARKERS]
    if any(m is not None and m.error for m in markers):
        # The ai-engine's judge queue retries transient failures and a re-run replaces these
        # assessments, so the label sync worker keeps re-checking recent failures.
        return "failed"
    if all(m is not None for m in markers):
        return "complete"
    if now - generated_at > stale_after:
        return "stale"  # the judge job never ran, died for good, or skipped this trace
    return "pending"

def _pct(v: float | None) -> str:
    return f"{v * 100:.0f}%" if v is not None else "—"

def _num(v: float | None) -> str:
    return f"{v:.0f}" if v is not None else "—"

def _grade(value: float | None, *, warn: float, bad: float) -> str:  # higher is worse
    if value is None:
        return "na"
    return "bad" if value > bad else "warn" if value > warn else "ok"

def _grade_low(value: float | None, *, warn: float, bad: float) -> str:  # lower is worse
    if value is None:
        return "na"
    return "bad" if value < bad else "warn" if value < warn else "ok"

def _tile(key: str, label: str, value: str, detail: str | None, severity: str) -> dict:
    return {"key": key, "label": label, "value": value, "detail": detail, "severity": severity}

def build_tiles(values: dict | None) -> list[dict]:
    v = values or {}
    weighted = v.get("severity_weighted_rate")
    return [
        _tile(
            "citation_grounding",
            "Citation grounding",
            _pct(v.get("grounded_rate")),
            f"Severity-weighted error {_pct(weighted)}" if weighted is not None else None,
            _grade(v.get("hallucination_rate"), warn=0.1, bad=0.25),
        ),
        _tile(
            "citations_removed",
            "Citations removed by code",
            _num(v.get("dropped_by_code")),
            "Fabricated identifiers dropped before judging",
            _grade(v.get("dropped_by_code"), warn=0, bad=2),
        ),
        _tile(
            "justification_integrity",
            "Justification integrity",
            _num(v.get("justification_contradictions")),
            "Justifications contradicting their own score",
            _grade(v.get("justification_contradictions"), warn=0, bad=0),
        ),
        _tile(
            "narrative_contradictions",
            "Narrative contradictions",
            _num(v.get("narrative_contradictions")),
            "Strengths, weaknesses and recommendations vs scores",
            _grade(v.get("narrative_contradictions"), warn=0, bad=2),
        ),
        _tile(
            "coverage",
            "Judge coverage",
            _pct(v.get("coverage")),
            "Citations the judge returned a verdict for",
            _grade_low(v.get("coverage"), warn=1.0, bad=0.8),
        ),
        _tile("tone", "Tone", "Not measured", "No tone judge runs in the pipeline yet", "na"),
    ]

def citation_check(values: dict | None) -> dict | None:
    if not values or values.get("grounded_rate") is None:
        return None
    flagged = (values.get("hallucination_rate") or 0) > 0.1 or (
        values.get("dropped_by_code") or 0
    ) > 0
    return {"status": "flagged" if flagged else "ok", "grounded_rate": values["grounded_rate"]}

def utcnow() -> datetime:
    return datetime.now(UTC)