from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ManualTextPayload(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    expectations_text: str = Field(min_length=1, max_length=5000)


class FileDiff(BaseModel):
    filename: str
    change_type: Literal["added", "modified", "deleted", "renamed"] = "modified"
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)


class CommitInfo(BaseModel):
    sha: str
    author: str
    author_email: str | None = None
    student_id: str | None = None
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
    sprint_id: str
    jira_project_key: str | None = None
    jql: str | None = None


class JiraTicket(BaseModel):
    ticket_id: str
    summary: str
    assignee: str | None = None
    status: str | None = None
    issue_type: str | None = None
    story_points: float | None = Field(default=None, ge=0)
    sprint_id: str | None = None
    timestamp: datetime | None = None


class JiraCleanedSnapshot(BaseModel):
    normalization_version: str
    source: str = "jira"
    jira_project_key: str
    course_id: str
    project_id: str
    sprint_id: str
    captured_at: datetime
    tickets: list[JiraTicket]


class JiraIngestionRun(BaseModel):
    run_id: str
    course_id: str
    project_id: str
    sprint_id: str
    jira_project_key: str
    jql: str
    raw_bucket: str
    raw_object_key: str
    issue_count: int = Field(ge=0)
    captured_at: datetime
    processed_at: datetime | None = None
    processing_status: Literal["pending", "completed", "failed"] = "pending"
    normalization_version: str | None = None
    processing_error: str | None = None


class AssessRequest(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    model_name: str | None = None


class AssessmentJobRecord(BaseModel):
    job_id: str
    course_id: str
    project_id: str
    sprint_id: str
    model_name: str | None = None
    status: str = "queued"
    progress: int = 0
    current_stage: str = "queued"
    report_id: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class AssessmentJobEvent(BaseModel):
    event: str
    data: dict


class RubricDimensionScoreDetail(BaseModel):
    score: float | int
    justification: str | None = None
    evidence_citations: list[str] = Field(default_factory=list)


class StudentScore(BaseModel):
    student_id: str
    score: float
    rationale: str


class TeamScore(BaseModel):
    score: float
    rationale: str
    # Default "" keeps old DB rows (persisted before this field existed) valid.
    overall_grade: str = ""


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
    rubric_scores: dict[str, RubricDimensionScoreDetail] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str]


class RubricWeightsPayload(BaseModel):
    """Body for setting a course's custom rubric dimension weights."""
    weights: dict[str, float]


class RubricWeightsResponse(BaseModel):
    course_id: str
    weights: dict[str, float]
    # False when no faculty override exists yet and this is just the default.
    is_custom: bool
    updated_by: str | None = None
    updated_at: datetime | None = None


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
