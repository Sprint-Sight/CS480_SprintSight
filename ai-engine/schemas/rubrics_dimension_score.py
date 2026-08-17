from pydantic import BaseModel, Field
from typing import Literal
   
class RubricDimensionScore(BaseModel):
    dimension: Literal["code_quality", "testing", "documentation", 
                        "requirements", "collaboration"]
    score: int = Field(ge=1, le=10)
    justification: str = Field(min_length=10)
    evidence_citations: list[str]  # specific file:line or Jira ticket refs
    strengths: list[str]
    areas_for_improvement: list[str]