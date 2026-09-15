from typing import Optional
from pydantic import BaseModel, Field, computed_field
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.member_contribution import MemberContribution
from schemas.rubrics_score import RubricsScore

class SprintAssessment(BaseModel):
    sprint_id: str
    team_id: str
    prompt_version: str # links to prompt registry
    overall_score: int = Field(ge=1, le=10)
    rubric_scores: RubricsScore
    member_contributions: list[MemberContribution] = [] # Set a default empty list here, making this optional
    executive_summary: str
    key_recommendations: list[str]
    # failed_dimensions: list[str] = Field(default_factory=list) REPLACED W THE @property BELOW

    @computed_field
    @property
    def failed_dimensions(self) -> list[str]: # computes from the rubric_scores attribute
        return self.rubric_scores.failed_dimensions