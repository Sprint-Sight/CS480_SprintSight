"""Schemas for Jira contribution outlier reporting.

The reports are instructor-facing (or intended to be fed to the AI engine), so
they include the raw evidence behind each metric: the Jira tickets that make up
a student's contribution total.
"""

from pydantic import BaseModel, Field


class JiraContributionTicketEvidence(BaseModel):
    """A single Jira ticket that contributed to a student's point total."""

    ticket_id: str = Field(..., description="Jira issue key, e.g. PROJ-123.")
    summary: str = Field(default="", description="Issue summary.")
    story_points: float = Field(
        default=0.0, description="Story points recorded for this ticket."
    )
    status: str | None = Field(default=None, description="Jira issue status.")
    issue_type: str | None = Field(default=None, description="Jira issue type.")
    project_id: str | None = Field(
        default=None, description="SprintSight project the ingestion run belongs to."
    )
    sprint_id: str | None = Field(
        default=None, description="Sprint associated with the ingestion run."
    )


class JiraContributionOutlierResponse(BaseModel):
    """Outlier information for a student's Jira contribution."""

    student_id: str = Field(..., description="UUID of the student.")
    student_full_name: str = Field(..., description="Display name of the student.")
    course_id: str = Field(..., description="UUID of the course.")
    project_id: str | None = Field(
        default=None,
        description="Project group the student belongs to, when one can be resolved.",
    )

    # ---- Raw Jira metrics -------------------------------------------------
    total_tickets: int = Field(
        ..., description="Number of Jira tickets assigned to the student."
    )
    total_story_points: float = Field(
        ..., description="Sum of story points across those tickets."
    )
    average_points_per_ticket: float = Field(
        ...,
        description="Mean story points per ticket (0 when the student has no tickets).",
    )

    # ---- Course-wide baseline (computed over all enrolled students) --------
    course_average_total_points: float | None = Field(
        ...,
        description="Mean total story points across all enrolled students. "
        "Students without Jira data count as zero.",
    )
    course_total_score_std_dev: float | None = Field(
        ...,
        description="Population standard deviation of total story points across "
        "enrolled students. Null when the course has fewer than two students.",
    )

    # ---- Outlier calculation (1-sample z-score) ---------------------------
    contribution_z_score: float | None = Field(
        default=None,
        description="z-score = (student_total - course_mean) / course_sd. "
        "Null when standard deviation is unavailable or zero.",
    )
    is_contribution_outlier: bool = Field(
        ...,
        description="True when |z| >= 1.0 (configurable via OUTLIER_Z_THRESHOLD).",
    )
    outlier_direction: str | None = Field(
        default=None,
        description='"low" if the student’s total is below the course average, '
        '"high" if above.',
    )

    # ---- Helpful counts ----------------------------------------------------
    students_below_course_average: int = Field(
        ...,
        description="Number of enrolled students whose total story points are "
        "below the course average.",
    )
    enrolled_student_count: int = Field(
        ...,
        description="Total number of students enrolled in the course.",
    )
    students_with_jira_data: int = Field(
        default=0,
        description="Number of enrolled students with at least one Jira ticket.",
    )

    # ---- Evidence ----------------------------------------------------------
    tickets: list[JiraContributionTicketEvidence] = Field(
        default_factory=list,
        description="Jira tickets used to compute this student's total.",
    )


class JiraContributionOutlierReport(BaseModel):
    """Course-wide Jira contribution analysis with per-student evidence."""

    course_id: str
    course_average_total_points: float | None
    course_total_score_std_dev: float | None
    enrolled_student_count: int
    students_with_jira_data: int
    students_below_course_average: int
    outlier_count: int = Field(
        ..., description="Number of students flagged as contribution outliers."
    )
    students: list[JiraContributionOutlierResponse]
