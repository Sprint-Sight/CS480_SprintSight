from pydantic import BaseModel, Field, computed_field

from schemas.member_contribution import MemberContribution
from schemas.rubrics_score import RubricsScore


class SprintAssessment(BaseModel):
    sprint_id: str
    team_id: str
    # Float, not rounded to an int: the backend multiplies this by 10 for its
    # /100 team_score, so rounding here to a 1-10 integer first would collapse
    # the /100 score down to multiples of 10 and throw away real resolution.
    overall_score: float = Field(ge=0, le=10)
    rubric_scores: RubricsScore
    member_contributions: list[MemberContribution] = [] # Set a default empty list here, making this optional
    executive_summary: str
    strengths: list[str] = []
    weaknesses: list[str] = []
    key_recommendations: list[str]
    prompt_version: str | None = None  # links to prompt registry
    # MLflow trace of the grading run. The backend stores it with the report so a
    # report can later be joined to its judge verdict (the judge runs after this
    # response is sent, so the verdict cannot travel in the response itself).
    trace_id: str | None = None
    # MLflow experiment that trace lives in. Set by api/assessment.py; research scripts leave it unset.
    experiment_name: str | None = None
    # failed_dimensions: list[str] = Field(default_factory=list) REPLACED W THE @property BELOW

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failed_dimensions(self) -> list[str]: # computes from the rubric_scores attribute
        return self.rubric_scores.failed_dimensions

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evaluation_failed(self) -> bool:
        """True when any dimension could not be scored. Consumers must then treat the
        placeholder score on that dimension as 'not assessed', never as a real score."""
        return bool(self.failed_dimensions)
