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


class PeerEvaluationUpdate(BaseModel):
    """Request to update an existing peer evaluation (score and/or remarks)."""

    score: int | None = Field(
        default=None, ge=1, le=5, description="Rating from 1 to 5."
    )
    remarks: str | None = Field(
        default=None, max_length=1000, description="Optional remarks about the member."
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


class PeerEvaluationReceivedItem(PeerEvaluationInstructorView):
    """One teammate's evaluation of a member, with score-outlier flags."""

    is_score_outlier: bool = Field(
        ...,
        description="True when this score is at least one standard deviation from the member's mean received score.",
    )
    score_z_score: float | None = Field(
        default=None,
        description="Z-score of this rating versus the member's other received scores.",
    )


class MemberPeerEvaluationDetail(BaseModel):
    """Evaluations a group member received from teammates, plus course-level stats."""

    course_id: str
    project_id: str
    project_name: str
    member_id: str
    member_email: str
    member_full_name: str
    evaluations: list[PeerEvaluationReceivedItem] = Field(
        ...,
        description="Scores and remarks from each teammate who evaluated this member.",
    )
    total_score: int = Field(..., description="Sum of scores this member received.")
    average_score: float | None
    evaluation_count: int
    is_total_outlier: bool = Field(
        ...,
        description="True when this member's total is at least one standard deviation from the course mean of received totals.",
    )
    total_z_score: float | None
    outlier_direction: str | None = Field(
        default=None,
        description='"low" or "high" when is_total_outlier is true.',
    )
    course_average_total: float | None = Field(
        default=None,
        description="Mean total received score among enrolled students who have at least one evaluation.",
    )
    course_total_score_std_dev: float | None
    enrolled_student_count: int
    students_with_received_evaluations: int
    students_below_course_average: int = Field(
        ...,
        description="Enrolled students whose received total is below the course average total.",
    )


class EvaluationStatusResponse(BaseModel):
    """Whether the current student can submit evaluations right now."""

    can_evaluate: bool
    is_open: bool
    opens_at: datetime | None
    expires_at: datetime | None
    message: str
