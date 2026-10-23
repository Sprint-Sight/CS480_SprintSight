"""Pydantic schemas for the report export feature."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ExportFormat(StrEnum):
    PDF = "pdf"
    CSV = "csv"


class ExportRequest(BaseModel):
    """Request to generate an assessment report export."""

    course_id: str = Field(..., description="Course offering ID.")
    project_id: str = Field(..., description="Project group ID.")
    sprint_id: str = Field(..., description="Sprint identifier.")
    format: ExportFormat = Field(
        default=ExportFormat.PDF,
        description="Export format: pdf or csv.",
    )
    include_student_emails: bool = Field(
        default=False,
        description=(
            "Include student email addresses in the export. "
            "Only set to true when explicitly authorized."
        ),
    )


class ExportPreviewResponse(BaseModel):
    """Basic assessment data returned for the UI preview before export."""

    report_id: str
    course_id: str
    project_id: str
    sprint_id: str
    generated_at: datetime
    team_score: float
    team_grade: str
    student_count: int
    recommendation_count: int
    strengths_count: int
    weaknesses_count: int


class ExportResponse(BaseModel):
    """Response returned after a successful export generation."""

    download_url: str = Field(..., description="URL to download the exported file.")
    expires_at: datetime = Field(
        ..., description="Timestamp after which the download link expires."
    )
    format: ExportFormat
    report_id: str
    include_student_emails: bool
    file_size_bytes: int


class ExportLogRecord:
    """A single export log entry."""

    def __init__(
        self,
        log_id: str,
        user_id: str,
        report_type: str,
        course_id: str,
        project_id: str,
        sprint_id: str,
        include_student_emails: bool,
        download_token: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        self.log_id = log_id
        self.user_id = user_id
        self.report_type = report_type
        self.course_id = course_id
        self.project_id = project_id
        self.sprint_id = sprint_id
        self.include_student_emails = include_student_emails
        self.download_token = download_token
        self.expires_at = expires_at
        self.created_at = created_at
