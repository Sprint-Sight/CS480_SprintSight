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

# Safe, short sentences for the engine's failure codes (mirrors ai-engine schemas/failure_class.py).
FAILURE_DESCRIPTIONS = {
    "schema_validation": "The judge model's answer did not match the required format.",
    "output_length": "The judge model's answer kept exceeding the length limit.",
    "timeout": "The judge model did not respond in time.",
    "infra_unavailable": "The judge model service was unavailable.",
    "context_truncated": "The evidence did not fit in the judge model's context window.",
    "remote_judge_disabled": "The judge model is not configured for this deployment.",
    "skipped_all_dimensions_failed": "Every rubric dimension failed, so nothing was judged.",
    "retries_exhausted": "The judge gave up after repeated attempts.",
    "unknown": "The judge failed for an unexpected reason.",
}
SKIPPED_TAG, DEAD_TAG = "judge.skipped", "judge.dead"


def failure_class(summary: TraceSummary) -> str | None:
    """Why the judge did not finish, as a short code, or None when nothing says it failed."""
    recorded = summary.assessment("citation_judge_failure_class")
    if recorded and recorded.text:
        return recorded.text
    if SKIPPED_TAG in summary.judge_tags:
        return "skipped_all_dimensions_failed"
    if DEAD_TAG in summary.judge_tags:
        return summary.judge_tags[DEAD_TAG] or "retries_exhausted"
    return None


def failure_description(code: str | None) -> str | None:
    if not code:
        return None
    return FAILURE_DESCRIPTIONS.get(code, FAILURE_DESCRIPTIONS["unknown"])


def judge_values(summary: TraceSummary) -> dict:
    values: dict = {}
    for key, name in SUMMARY_FIELDS.items():
        assessment = summary.assessment(name)
        values[key] = assessment.value if assessment else None
    values["trace_duration_ms"] = summary.duration_ms
    values["failure_class"] = failure_class(summary)
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
    if SKIPPED_TAG in summary.judge_tags or DEAD_TAG in summary.judge_tags:
        return "failed"  # the engine skipped this trace or gave up on it: it will not finish
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
        # Tone judge can be added in the future.
        # _tile("tone", "Tone", "Not measured", "No tone judge runs in the pipeline yet", "na"),
    ]

def citation_check(values: dict | None) -> dict | None:
    if not values or values.get("grounded_rate") is None:
        return None
    flagged = (values.get("hallucination_rate") or 0) > 0.1 or (
        values.get("dropped_by_code") or 0
    ) > 0
    return {"status": "flagged" if flagged else "ok", 
            "grounded_rate": values["grounded_rate"],
            "hallucination_rate": values.get("hallucination_rate"), 
            "dropped_by_code": values.get("dropped_by_code")
        }

def utcnow() -> datetime:
    return datetime.now(UTC)