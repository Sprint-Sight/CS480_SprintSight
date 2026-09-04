from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ManualTextPayload(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    expectations_text: str = Field(min_length=10, max_length=5000)


class FileDiff(BaseModel):
    filename: str
    change_type: Literal["added", "modified", "deleted", "renamed"] = "modified"
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)


class CommitInfo(BaseModel):
    sha: str
    author: str
    message: str
    timestamp: datetime
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)
    files_changed: list[FileDiff] = Field(default_factory=list)


class PaginationMetadata(BaseModel):
    limit: int | None
    offset: int | None
    total: int
    has_more: bool


class IngestionDataResponse(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    head_sha: str | None
    captured_at: datetime
    commit_frequency: float
    code_churn: int
    pr_turnaround_hours: float | None
    assigned_story_points: int | None
    completion_percent: float | None
    commits: list[CommitInfo]
    pagination: PaginationMetadata


class IngestionRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str


class JiraRawSyncRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    jira_project_key: str | None = Field(default=None, max_length=50)
    jql: str | None = Field(default=None, max_length=2000)


class AssessRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    model_name: Literal[
        "sprintsight-llama",
        "sprintsight-qwen",
        "sprintsight-mistral",
        "sprintsight-gemma",
        "sprintsight-grader",
    ] | None = None


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
