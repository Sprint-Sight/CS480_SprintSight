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


# Upper bound on citations per dimension (agreed with the team). Enforced by
# trimming in coerce_citations rather than by failing validation, so a model
# that over-cites loses its weakest tail instead of burning a retry.
MAX_EVIDENCE_CITATIONS = 15


class EvidenceCitation(BaseModel):
    identifier: str = Field(description="Verbatim citation anchor copied from Student Artifacts: a file/line anchor such as src/app.py:L10-L24 or src/app.py:L10-L24@abc1234, a commit SHA, a Jira ticket ID, a filename, or a metric value.")
    reason: str = Field(min_length=15, description="One short sentence tying this identifier to the score/feedback.")


CitationKind = Literal["file_lines", "diff_lines", "file", "commit", "ticket", "other"]


class ResolvedEvidenceCitation(EvidenceCitation):
    """A citation after services/grounding.resolve_citations has matched it
    to evidence the model was actually shown. Never asked of the model (it
    only writes `identifier` and `reason`); the location fields are filled in
    code so a client can link to the exact file and lines."""
    kind: CitationKind = "other"
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    commit_sha: str | None = None


def _normalize_citation(item: object) -> dict:
    # Already a well-formed citation (e.g. hand-authored gold data in
    # evaluation/benchmarks/, or a re-validated model). Without this, the
    # positional-guessing branch below falls through to str(item) and the
    # whole EvidenceCitation repr lands in `identifier` with an empty
    # `reason`, which then fails reason's min_length=15 at validation.
    if isinstance(item, EvidenceCitation):
        return item.model_dump()
    if isinstance(item, str):
        identifier, separator, reason = item.partition("|")
        return {"identifier": identifier.strip(), "reason": reason.strip() if separator else ""}
    if not isinstance(item, dict):
        return {"identifier": str(item), "reason": ""}
    if "identifier" in item and "reason" in item:
        return dict(item)  # already well-formed; keeps any resolved location fields

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
    evidence_citations: list[EvidenceCitation] = Field(max_length=MAX_EVIDENCE_CITATIONS)
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
        return [_normalize_citation(item) for item in value[:MAX_EVIDENCE_CITATIONS]]


class RubricDimensionScore(ModelOutput):
    """What the API actually stores/returns — adds the two fields the model
    never sees: `dimension` (assigned in code from the dimension that was
    requested) and `evaluation_failed` (set only by evaluator.py's fallback
    path, to guarantee every dimension is present even after a failure)."""
    # Same citations, after grounding has resolved each one to the file,
    # lines, commit, or ticket it points at.
    evidence_citations: list[ResolvedEvidenceCitation] = Field(  # type: ignore[assignment]
        default_factory=list, max_length=MAX_EVIDENCE_CITATIONS,
    )
    dimension: DimensionName
    # Set only by evaluator.py's fallback path, never by the model itself:
    # marks a synthesized placeholder used to guarantee all rubric dimensions are
    # always present, so callers can still distinguish it from a real score.
    evaluation_failed: bool = False
    # Only set alongside evaluation_failed (see schemas/failure_class.py): which
    # kind of failure exhausted the retries, and the full error text. The text is
    # for operators; `justification` carries only the short user-safe description.
    failure_class: str | None = None
    error_detail: str | None = None
    citations_dropped: int = 0  # how many citations were dropped: ungrounded (fabricated) identifiers removed by code, set in services/llm_client.py
    # Human-curated only (e.g. evaluation/benchmarks/ gold reference data) --
    # never asked of the model, same reasoning as ModelOutput's docstring above.
    strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
