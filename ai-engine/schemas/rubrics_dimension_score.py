from pydantic import BaseModel, Field, field_validator
from typing import Literal

# Keys the model has been observed using instead of "identifier"/"reason" —
# including literally copying the prompt's own format description as key
# names (e.g. "verbatim identifier", "one short sentence explaining why...").
# Matched by substring so near-miss phrasing still normalizes correctly.
_IDENTIFIER_KEY_HINTS = ("identifier", "sha", "commit", "ticket", "citation", "text", "value", "id")
_REASON_KEY_HINTS = ("reason", "sentence", "explan", "justif", "why", "evidence")


class EvidenceCitation(BaseModel):
    identifier: str = Field(description="Verbatim commit SHA, Jira ticket ID, filename, or metric value copied from Student Artifacts.")
    reason: str = Field(default="", description="One short sentence tying this identifier to the score/feedback.")


def _normalize_citation(item: object) -> dict:
    if isinstance(item, str):
        identifier, separator, reason = item.partition("|")
        return {"identifier": identifier.strip(), "reason": reason.strip() if separator else ""}
    if not isinstance(item, dict):
        return {"identifier": str(item), "reason": ""}

    remaining = dict(item)
    identifier_value = None
    reason_value = None
    for key in list(remaining):
        lowered_key = key.lower()
        if identifier_value is None and any(hint in lowered_key for hint in _IDENTIFIER_KEY_HINTS):
            identifier_value = remaining.pop(key)
        elif reason_value is None and any(hint in lowered_key for hint in _REASON_KEY_HINTS):
            reason_value = remaining.pop(key)

    # Neither key name matched anything recognizable — fall back to
    # positional guessing from whatever values are left, in insertion order.
    leftover = list(remaining.values())
    if identifier_value is None and leftover:
        identifier_value = leftover.pop(0)
    if reason_value is None and leftover:
        reason_value = leftover.pop(0)

    return {
        "identifier": str(identifier_value) if identifier_value is not None else "",
        "reason": str(reason_value) if reason_value is not None else "",
    }


class RubricDimensionScore(BaseModel):
    dimension: Literal["code_quality", "testing", "documentation",
                        "requirements", "collaboration"]
    score: int = Field(ge=1, le=10)
    justification: str = Field(min_length=10)
    evidence_citations: list[EvidenceCitation]
    # Set only by evaluator.py's fallback path, never by the model itself:
    # marks a synthesized placeholder used to guarantee all 5 dimensions are
    # always present, so callers can still distinguish it from a real score.
    evaluation_failed: bool = False

    @field_validator("evidence_citations", mode="before")
    @classmethod
    def coerce_citations(cls, value):
        # However the model shapes each citation (plain string, "id | reason",
        # or a dict with arbitrary/self-invented key names), normalize it to
        # {"identifier", "reason"} instead of relying on the model to match
        # the schema exactly or on a retry to fix it.
        if not isinstance(value, list):
            return value
        return [_normalize_citation(item) for item in value]
