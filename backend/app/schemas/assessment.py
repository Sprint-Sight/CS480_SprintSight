from datetime import datetime

from pydantic import BaseModel, Field


class ManualTextPayload(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    expectations_text: str = Field(min_length=10, max_length=5000)


class IngestionRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str


class AssessRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str


class StudentScore(BaseModel):
    student_id: str
    score: float
    rationale: str


class TeamScore(BaseModel):
    score: float
    rationale: str


class AssessmentReport(BaseModel):
    report_id: str
    model_name: str
    mode: str
    course_id: str
    project_id: str
    sprint_id: str
    generated_at: datetime
    rubric_weights: dict[str, float]
    team_score: TeamScore
    individual_scores: list[StudentScore]
    recommendations: list[str]


class OverrideRequest(BaseModel):
    report_id: str
    student_id: str
    new_score: float = Field(ge=0.0, le=100.0)
    reason_comment: str = Field(min_length=5, max_length=2000)


class OverrideResponse(BaseModel):
    override_id: str
    report_id: str
    student_id: str
    original_score: float
    new_score: float
    reason_comment: str
    instructor_id: str
    created_at: datetime


class AuditRecord(BaseModel):
    override_id: str
    timestamp: datetime
    instructor_id: str
    student_id: str
    report_id: str
    original_score: float
    new_score: float
    reason_comment: str


class AssessRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    model_name: str = Field(default="sprintsight-llama")
