"""Pydantic schemas for the peer evaluation feature."""

from datetime import datetime

from pydantic import BaseModel, Field


class PeerEvaluationCreate(BaseModel):
    """Request to submit a peer evaluation of a group member."""

    project_id: str = Field(..., description="Project group ID.")
    rated_id: str = Field(..., description="ID of the student being evaluated.")
    score: int = Field(..., ge=1, le=5, description="Rating from 1 to 5.")
    remarks: str | None = Field(
        default=None, max_length=1000, description="Optional remarks about the member."
    )
    reason: str | None = Field(
        default=None, max_length=1000, description="Reason for the given score."
    )


class PeerEvaluationUpdate(BaseModel):
    """Request to update an existing peer evaluation (score and/or remarks)."""

    score: int | None = Field(
        default=None, ge=1, le=5, description="Rating from 1 to 5."
    )
    remarks: str | None = Field(
        default=None, max_length=1000, description="Optional remarks about the member."
    )
    reason: str | None = Field(
        default=None, max_length=1000, description="Reason for the given score."
    )


class PeerEvaluationResponse(BaseModel):
    """A single peer evaluation returned to the rater (student's own submissions)."""

    evaluation_id: str
    course_id: str
    project_id: str
    rater_id: str
    rated_id: str
    score: int
    remarks: str | None
    reason: str | None = None
    created_at: datetime


class PeerEvaluationInstructorView(BaseModel):
    """A peer evaluation as seen by an instructor (includes rater identity)."""

    evaluation_id: str
    course_id: str
    project_id: str
    rater_id: str
    rater_email: str
    rater_full_name: str
    rated_id: str
    rated_email: str
    rated_full_name: str
    score: int
    remarks: str | None
    reason: str | None = None
    created_at: datetime


class PeerEvaluationConfigCreate(BaseModel):
    """Request to open/close peer evaluation for a course."""

    is_open: bool = Field(..., description="Whether peer evaluation is currently open.")
    opens_at: datetime | None = Field(
        default=None,
        description="Date when peer evaluation opens. If null and is_open=True, opens immediately.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Expiry date after which students cannot submit evaluations.",
    )


class PeerEvaluationConfigResponse(BaseModel):
    """Peer evaluation configuration for a course."""

    course_id: str
    is_open: bool
    opens_at: datetime | None
    expires_at: datetime | None
    updated_by: str
    updated_at: datetime


class PeerEvaluationSummary(BaseModel):
    """Summary of evaluations for a project (instructor view)."""

    project_id: str
    project_name: str
    total_evaluations: int
    average_score: float | None
    evaluations: list[PeerEvaluationInstructorView]


class CoursePeerEvaluationSummary(BaseModel):
    """Summary of all peer evaluations in a course (instructor view)."""

    course_id: str
    course_code: str
    is_open: bool
    expires_at: datetime | None
    total_projects: int
    total_evaluations: int
    projects: list[PeerEvaluationSummary]


class EvaluationStatusResponse(BaseModel):
    """Whether the current student can submit evaluations right now."""

    can_evaluate: bool
    is_open: bool
    opens_at: datetime | None
    expires_at: datetime | None
    message: str
