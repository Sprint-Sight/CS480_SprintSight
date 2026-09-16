from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import Literal
from services.grounding import find_ungrounded_citations

class RubricDimensionScore(BaseModel):
    dimension: Literal["code_quality", "testing", "documentation",
                        "requirements", "collaboration"]
    score: int = Field(ge=1, le=10)
    justification: str = Field(min_length=10)
    evidence_citations: list[str]  # specific file:line or Jira ticket refs

    @field_validator("evidence_citations", mode="before")
    @classmethod
    def coerce_citation_strings(cls, value):
        # Models routinely wrap citations as {"text": "..."} despite the prompt's
        # explicit instruction not to (~30% of real calls) -- normalize instead of
        # relying on a retry to fix it.
        if not isinstance(value, list):
            return value
        coerced = []
        for item in value:
            if isinstance(item, str):
                coerced.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("citation") or item.get("value")
                coerced.append(text if isinstance(text, str) else str(item))
            else:
                coerced.append(str(item))
        return coerced

    @field_validator("evidence_citations")
    @classmethod
    def citations_must_be_grounded(cls, value: list[str], info: ValidationInfo) -> list[str]:
        # Runs after coerce_citation_strings, once the field is a list[str].
        # `bundle_data` is supplied via validation_context in llm_client.py's
        # `create()` call. If any citation can't be traced back to it, raising
        # here lets instructor re-ask the model with this exact error message
        # and retry (within max_retries) instead of just failing after the
        # fact -- this is what actually corrects fabricated evidence rather
        # than only detecting it.
        bundle_data = (info.context or {}).get("bundle_data") if info.context else None
        if not bundle_data:
            # No context supplied (e.g. a unit test constructing this model
            # directly) -- skip rather than block unrelated code paths.
            return value
        ungrounded = find_ungrounded_citations(bundle_data, value)
        if ungrounded:
            raise ValueError(
                "These citations do not appear anywhere in the student "
                "artifact bundle and look fabricated or copied from example "
                f"text -- remove them or replace with real evidence actually "
                f"present in the bundle: {ungrounded!r}"
            )
        return value