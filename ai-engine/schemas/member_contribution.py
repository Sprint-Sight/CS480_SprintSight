from pydantic import BaseModel, Field

class MemberContribution(BaseModel):
    student_id: str
    contribution_score: int = Field(ge=1, le=10)
    primary_contributions: list[str]
    evidence: list[str]