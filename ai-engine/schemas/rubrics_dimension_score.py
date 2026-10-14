from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Keys the model has been observed using instead of "identifier"/"reason" —
# including literally copying the prompt's own format description as key
# names (e.g. "verbatim identifier", "one short sentence explaining why...").
# Matched by substring so near-miss phrasing still normalizes correctly.
# "id"/"text"/"value" were removed from the identifier hints: "id" is a
# substring of "evidence" ("ev-id-ence"), so a key literally named "evidence"
# was being classified as the identifier before the reason check ever ran.
_IDENTIFIER_KEY_HINTS = ("identifier", "sha", "commit", "ticket", "citation")
_REASON_KEY_HINTS = ("reason", "sentence", "explan", "justif", "why", "evidence")

# Shared across schemas/rubrics_score.py, prompts/dimension_criteria.py, and
# services/llm_client.py so a rubric dimension name is always one of these
# six values wherever it's typed, instead of a plain (unchecked) str.
DimensionName = Literal["code_quality", "testing", "documentation",
                         "requirements", "collaboration", "cicd"]


class EvidenceCitation(BaseModel):
    identifier: str = Field(description="Verbatim commit SHA, Jira ticket ID, filename, or metric value copied from Student Artifacts.")
    reason: str = Field(min_length=15, description="One short sentence tying this identifier to the score/feedback.")


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


class ModelOutput(BaseModel):
    """
    The ONLY schema the model is asked to produce (see llm_client.py's
    `response_model=ModelOutput`). `dimension` and `evaluation_failed` are
    deliberately excluded here: the caller already knows which dimension it
    requested and assigns it in code, and `evaluation_failed` is only ever
    set by evaluator.py's fallback path. Handing the model a 6-value enum to
    echo back and a bool it should always answer False just gives it more
    prompt surface to copy instead of reading the evidence.

    Field order is deliberate: `justification`/`evidence_citations` come
    before `score` so the model has to write its reasoning and cite real
    evidence BEFORE committing to a number, instead of picking a score first
    and writing a justification to match it.
    """
    justification: str = Field(min_length=10, max_length=500)
    evidence_citations: list[EvidenceCitation] = Field(max_length=3)
    score: int = Field(ge=1, le=10)

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


class RubricDimensionScore(ModelOutput):
    """What the API actually stores/returns — adds the two fields the model
    never sees: `dimension` (assigned in code from the dimension that was
    requested) and `evaluation_failed` (set only by evaluator.py's fallback
    path, to guarantee every dimension is present even after a failure)."""
    dimension: DimensionName
    # Set only by evaluator.py's fallback path, never by the model itself:
    # marks a synthesized placeholder used to guarantee all rubric dimensions are
    # always present, so callers can still distinguish it from a real score.
    evaluation_failed: bool = False
    citations_dropped: int = 0  # how many citations were dropped because they were duplicates or too long (max 3 kept)
    # Human-curated only (e.g. schemas/benchmark.py's gold reference data) --
    # never asked of the model, same reasoning as ModelOutput's docstring above.
    strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
