from pydantic import BaseModel, Field, field_validator
from typing import Literal

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