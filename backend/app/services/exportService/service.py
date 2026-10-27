"""Export service: generates PDF/CSV assessment reports with watermarks,
rate limiting, and export logging.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app.repositories.interfaces import (
    AssessmentRepository,
    ExportLogRepository,
    ProjectRepository,
    UserRepository,
)
from app.schemas.auth import Role
from app.schemas.export import (
    ExportFormat,
    ExportLogRecord,
    ExportRequest,
    ExportResponse,
)
from app.services.auditLogService.service import append_action_audit

EXPORT_RATE_LIMIT = 5
EXPORT_RATE_WINDOW_SECONDS = 60
DOWNLOAD_LINK_TTL_SECONDS = 3600  # 1 hour


class ExportService:
    def __init__(
        self,
        export_log_repository: ExportLogRepository,
        assessment_repository: AssessmentRepository | None = None,
        project_repository: ProjectRepository | None = None,
        user_repository: UserRepository | None = None,
    ) -> None:
        self._export_log_repository = export_log_repository
        self._assessment_repository = assessment_repository
        self._project_repository = project_repository
        self._user_repository = user_repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_export(
        self,
        request: ExportRequest,
        current_user_id: str,
        action_audits,
    ) -> ExportResponse:
        """Generate a PDF or CSV export, enforce rate limits, and log the export."""

        # Rate limit: max 5 exports per minute per instructor.
        self._enforce_rate_limit(current_user_id)

        expires_at = datetime.now(UTC) + timedelta(seconds=DOWNLOAD_LINK_TTL_SECONDS)
        download_token = str(uuid4())

        # Locate the latest assessment report for the course/project/sprint.
        report = self._get_report(
            request.course_id, request.project_id, request.sprint_id
        )
        if report is None:
            raise ValueError(
                f"No assessment report found for course {request.course_id}, "
                f"project {request.project_id}, sprint {request.sprint_id}."
            )

        if request.format == ExportFormat.PDF:
            file_bytes = self._build_pdf(
                report,
                include_student_emails=request.include_student_emails,
            )
        else:
            file_bytes = self._build_csv(
                report,
                include_student_emails=request.include_student_emails,
            )

        # Store the generated file bytes keyed by the download token so the
        # download endpoint can serve them later.
        _EXPORT_STORE[download_token] = (file_bytes, expires_at, request.format)

        # Log the export (user ID, report type, timestamp).
        log_record = ExportLogRecord(
            log_id=str(uuid4()),
            user_id=current_user_id,
            report_type=request.format.value,
            course_id=request.course_id,
            project_id=request.project_id,
            sprint_id=request.sprint_id,
            include_student_emails=request.include_student_emails,
            download_token=download_token,
            expires_at=expires_at,
            created_at=datetime.now(UTC),
        )
        self._export_log_repository.create_log(log_record)

        # Audit trail.
        append_action_audit(
            action_audits,
            actor_id=current_user_id,
            actor_role=Role.INSTRUCTOR.value,
            action=f"export_{request.format.value}",
            target_type="assessment_report",
            target_id=report.report_id,
            details={
                "course_id": request.course_id,
                "project_id": request.project_id,
                "sprint_id": request.sprint_id,
                "include_student_emails": request.include_student_emails,
                "expires_at": expires_at.isoformat(),
            },
        )

        return ExportResponse(
            download_url=f"/api/v1/export/download/{download_token}",
            expires_at=expires_at,
            format=request.format,
            report_id=report.report_id,
            include_student_emails=request.include_student_emails,
            file_size_bytes=len(file_bytes),
        )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _enforce_rate_limit(self, user_id: str) -> None:
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=EXPORT_RATE_WINDOW_SECONDS)
        recent = self._export_log_repository.count_exports_since(user_id, window_start)
        if recent >= EXPORT_RATE_LIMIT:
            raise RateLimitError(
                f"Export rate limit exceeded: maximum {EXPORT_RATE_LIMIT} exports "
                f"per {EXPORT_RATE_WINDOW_SECONDS} seconds. Try again later."
            )

    # ------------------------------------------------------------------
    # Report retrieval
    # ------------------------------------------------------------------

    def _get_report(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
    ):
        repository = self._assessment_repository
        if repository is None:
            return None
        reports = repository.list_reports(course_id, project_id, sprint_id)
        return reports[0] if reports else None

    # ------------------------------------------------------------------
    # PDF generation
    # ------------------------------------------------------------------

    def _build_pdf(
        self,
        report,
        include_student_emails: bool,
    ) -> bytes:
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter

        # --- Header ---
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 60, "SprintSight Assessment Report")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, height - 80, f"Report ID: {report.report_id}")
        pdf.drawString(50, height - 95, f"Course: {report.course_id}")
        pdf.drawString(50, height - 110, f"Project: {report.project_id}")
        pdf.drawString(50, height - 125, f"Sprint: {report.sprint_id}")
        pdf.drawString(
            50,
            height - 140,
            f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        )

        y = height - 180

        # --- Team score ---
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Team Score")
        y -= 18
        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            70,
            y,
            f"Score: {report.team_score.score}  |  Grade: "
            f"{report.team_score.overall_grade or 'N/A'}",
        )
        pdf.drawString(70, y - 14, f"Rationale: {report.team_score.rationale}")
        y -= 40

        # --- Rubric breakdown ---
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Rubric Breakdown")
        y -= 18
        pdf.setFont("Helvetica", 10)
        if report.rubric_scores:
            for dimension, detail in report.rubric_scores.items():
                score = detail.score
                justification = detail.justification or ""
                pdf.drawString(70, y, f"{dimension}: {score}")
                wrapped = simpleSplit(justification, "Helvetica", 8, width - 140)
                for line in wrapped[:2]:
                    y -= 12
                    pdf.drawString(90, y, line)
                y -= 8
        else:
            pdf.drawString(70, y, "No rubric scores available.")
            y -= 14
        y -= 10

        # --- Individual scores ---
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Individual Scores")
        y -= 18
        pdf.setFont("Helvetica", 10)
        if report.individual_scores:
            for score in report.individual_scores:
                email = ""
                if include_student_emails and self._user_repository is not None:
                    user = self._user_repository.get_by_id(score.student_id)
                    email = f" ({user.email})" if user else ""
                line = f"Student {score.student_id}{email}: {score.score}"
                pdf.drawString(70, y, line)
                wrapped = simpleSplit(score.rationale, "Helvetica", 8, width - 140)
                for line in wrapped[:2]:
                    y -= 12
                    pdf.drawString(90, y, line)
                y -= 8
        else:
            pdf.drawString(70, y, "No individual scores available.")
            y -= 14
        y -= 10

        # --- Recommendations ---
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(50, y, "Recommendations")
        y -= 18
        pdf.setFont("Helvetica", 10)
        if report.recommendations:
            for rec in report.recommendations:
                wrapped = simpleSplit(f"- {rec}", "Helvetica", 10, width - 120)
                for line in wrapped:
                    y -= 14
                    pdf.drawString(70, y, line)
                y -= 6
        else:
            pdf.drawString(70, y, "No recommendations available.")
            y -= 14

        pdf.showPage()
        pdf.save()
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # CSV generation
    # ------------------------------------------------------------------

    def _build_csv(
        self,
        report,
        include_student_emails: bool,
    ) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        # Metadata.
        writer.writerow(["Report ID", report.report_id])
        writer.writerow(["Course", report.course_id])
        writer.writerow(["Project", report.project_id])
        writer.writerow(["Sprint", report.sprint_id])
        writer.writerow(["Generated", report.generated_at.isoformat()])
        writer.writerow([])

        # Team score.
        writer.writerow(["Team Score"])
        writer.writerow(["Score", report.team_score.score])
        writer.writerow(["Grade", report.team_score.overall_grade or "N/A"])
        writer.writerow(["Rationale", report.team_score.rationale])
        writer.writerow([])

        # Rubric breakdown.
        writer.writerow(["Rubric Breakdown"])
        writer.writerow(["Dimension", "Score", "Justification"])
        if report.rubric_scores:
            for dimension, detail in report.rubric_scores.items():
                writer.writerow(
                    [dimension, detail.score, detail.justification or ""]
                )
        else:
            writer.writerow(["No rubric scores available", "", ""])
        writer.writerow([])

        # Individual scores.
        writer.writerow(["Individual Scores"])
        header = ["Student ID", "Score", "Rationale"]
        if include_student_emails:
            header.insert(1, "Email")
        writer.writerow(header)
        if report.individual_scores:
            for score in report.individual_scores:
                row = [score.student_id, score.score, score.rationale]
                if include_student_emails and self._user_repository is not None:
                    user = self._user_repository.get_by_id(score.student_id)
                    email = user.email if user else ""
                    row.insert(1, email)
                writer.writerow(row)
        else:
            writer.writerow(["No individual scores available", "", ""])
        writer.writerow([])

        # Recommendations.
        writer.writerow(["Recommendations"])
        if report.recommendations:
            for rec in report.recommendations:
                writer.writerow([rec])
        else:
            writer.writerow(["No recommendations available"])

        return buffer.getvalue().encode("utf-8")


class RateLimitError(Exception):
    """Raised when the export rate limit is exceeded."""


# In-memory store for generated export files keyed by download token.
# In production this would be backed by object storage (e.g. MinIO/S3) with TTL.
_EXPORT_STORE: dict[str, tuple[bytes, datetime, ExportFormat]] = {}
