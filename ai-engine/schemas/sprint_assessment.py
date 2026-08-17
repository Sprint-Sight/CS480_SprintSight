from typing import Optional
from pydantic import BaseModel, Field
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.member_contribution import MemberContribution

class SprintAssessment(BaseModel):
    sprint_id: str
    team_id: str
    prompt_version: str # links to prompt registry
    overall_score: int = Field(ge=1, le=10)
    rubric_scores: list[RubricDimensionScore]
    member_contributions: list[MemberContribution] = [] # Set a default empty list here, making this optional
    executive_summary: str
    key_recommendations: list[str]