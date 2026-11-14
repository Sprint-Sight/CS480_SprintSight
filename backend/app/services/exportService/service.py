"""Export service: generates PDF/CSV assessment reports with watermarks,
rate limiting, and export logging.
"""

from __future__ import annotations

import csv
import html
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import reportlab  # type: ignore
from reportlab.lib import colors  # type: ignore
from reportlab.lib.enums import TA_RIGHT  # type: ignore
from reportlab.lib.pagesizes import letter  # type: ignore
from reportlab.lib.styles import ParagraphStyle  # type: ignore
from reportlab.pdfbase import pdfmetrics  # type: ignore
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore
from reportlab.platypus import (  # type: ignore
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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
_PDF_FONT = "SprintSightSans"
_PDF_FONT_BOLD = "SprintSightSans-Bold"
_PDF_FONT_DIR = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont(_PDF_FONT, str(_PDF_FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(_PDF_FONT_BOLD, str(_PDF_FONT_DIR / "VeraBd.ttf")))
pdfmetrics.registerFontFamily(
    _PDF_FONT,
    normal=_PDF_FONT,
    bold=_PDF_FONT_BOLD,
    italic=_PDF_FONT,
    boldItalic=_PDF_FONT_BOLD,
)


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
        report = self._get_report(request.course_id, request.project_id, request.sprint_id)
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
        page_width, _ = letter
        left_margin = 58
        right_margin = 58
        content_width = page_width - left_margin - right_margin
        neutral = colors.HexColor("#777777")
        light_neutral = colors.HexColor("#D1D1D1")
        pale_neutral = colors.HexColor("#F3F3F3")

        styles = {
            "title": ParagraphStyle(
                "ExportTitle",
                fontName=_PDF_FONT_BOLD,
                fontSize=17,
                leading=21,
                textColor=colors.black,
                spaceAfter=8,
            ),
            "section": ParagraphStyle(
                "ExportSection",
                fontName=_PDF_FONT_BOLD,
                fontSize=12,
                leading=15,
                textColor=colors.black,
                spaceBefore=12,
                spaceAfter=6,
                keepWithNext=True,
            ),
            "category": ParagraphStyle(
                "ExportCategory",
                fontName=_PDF_FONT_BOLD,
                fontSize=10,
                leading=13,
                textColor=colors.black,
            ),
            "score": ParagraphStyle(
                "ExportScore",
                fontName=_PDF_FONT_BOLD,
                fontSize=9,
                leading=12,
                alignment=TA_RIGHT,
                textColor=colors.black,
            ),
            "body": ParagraphStyle(
                "ExportBody",
                fontName=_PDF_FONT,
                fontSize=9,
                leading=13,
                textColor=colors.black,
                splitLongWords=1,
            ),
            "evidence": ParagraphStyle(
                "ExportEvidence",
                fontName=_PDF_FONT,
                fontSize=8,
                leading=11,
                leftIndent=8,
                rightIndent=6,
                spaceBefore=3,
                spaceAfter=3,
                borderPadding=4,
                backColor=pale_neutral,
                textColor=colors.black,
                splitLongWords=1,
            ),
            "meta": ParagraphStyle(
                "ExportMeta",
                fontName=_PDF_FONT,
                fontSize=8,
                leading=11,
                textColor=colors.black,
                splitLongWords=1,
            ),
            "card": ParagraphStyle(
                "ExportCard",
                fontName=_PDF_FONT,
                fontSize=9,
                leading=13,
                textColor=colors.black,
                splitLongWords=1,
            ),
        }

        def paragraph(value: object, style_name: str = "body") -> Paragraph:
            escaped = html.escape(str(value or "")).replace("\n", "<br/>")
            return Paragraph(escaped or " ", styles[style_name])

        def labeled_paragraph(
            label: str,
            value: object,
            style_name: str,
        ) -> Paragraph:
            escaped = html.escape(str(value or "")).replace("\n", "<br/>")
            return Paragraph(
                f"<b>{html.escape(label)}</b> {escaped or ' '}",
                styles[style_name],
            )

        def section_heading(title: str) -> list[object]:
            return [
                Paragraph(html.escape(title), styles["section"]),
                HRFlowable(
                    width="100%",
                    thickness=0.6,
                    color=light_neutral,
                    spaceAfter=7,
                ),
            ]

        def draw_footer(pdf_canvas: canvas.Canvas, _document) -> None:
            pdf_canvas.saveState()
            pdf_canvas.setStrokeColor(light_neutral)
            pdf_canvas.setLineWidth(0.5)
            pdf_canvas.line(left_margin, 38, page_width - right_margin, 38)
            pdf_canvas.setFont(_PDF_FONT, 8)
            pdf_canvas.setFillColor(neutral)
            pdf_canvas.drawString(left_margin, 25, "SprintSight Assessment Report")
            pdf_canvas.drawRightString(
                page_width - right_margin,
                25,
                f"Page {pdf_canvas.getPageNumber()}",
            )
            pdf_canvas.restoreState()

        story: list[object] = [
            Paragraph("SprintSight Assessment Report", styles["title"]),
        ]
        generated_at = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        metadata = [
            [
                paragraph(f"Report ID: {report.report_id}", "meta"),
                paragraph(f"Course: {report.course_id}", "meta"),
            ],
            [
                paragraph(f"Project: {report.project_id}", "meta"),
                paragraph(f"Sprint: {report.sprint_id}", "meta"),
            ],
            [
                paragraph(f"Generated: {generated_at}", "meta"),
                paragraph("", "meta"),
            ],
        ]
        metadata_card = Table(
            metadata,
            colWidths=[content_width / 2, content_width / 2],
            hAlign="LEFT",
        )
        metadata_card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, light_neutral),
                    ("BACKGROUND", (0, 0), (-1, -1), pale_neutral),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([metadata_card, Spacer(1, 5)])

        story.extend(section_heading("Team Score"))
        team_score_header = Table(
            [[paragraph(f"Score: {report.team_score.score}", "category")]],
            colWidths=[content_width],
        )
        team_score_header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), pale_neutral),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.6, light_neutral),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend(
            [
                team_score_header,
                Spacer(1, 5),
                labeled_paragraph("Rationale:", report.team_score.rationale, "card"),
            ]
        )

        story.extend(section_heading("Rubric Breakdown"))
        if report.rubric_scores:
            labels = {
                "requirements": "Requirements",
                "code_quality": "Code Quality",
                "testing": "Testing",
                "documentation": "Documentation",
                "collaboration": "Collaboration",
                "cicd": "CI/CD",
                "delivery": "Delivery",
                "quality": "Quality",
            }
            for dimension, detail in report.rubric_scores.items():
                label = labels.get(
                    dimension.lower(),
                    dimension.replace("_", " ").title(),
                )
                category_header = Table(
                    [
                        [
                            paragraph(label, "category"),
                            paragraph(f"Score: {detail.score}", "score"),
                        ]
                    ],
                    colWidths=[content_width * 0.78, content_width * 0.22],
                )
                category_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), pale_neutral),
                            ("LINEBELOW", (0, 0), (-1, 0), 0.6, light_neutral),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.extend(
                    [
                        category_header,
                        Spacer(1, 5),
                        labeled_paragraph(
                            "Justification:",
                            detail.justification or "",
                            "card",
                        ),
                        Spacer(1, 4),
                    ]
                )
                if detail.evidence_citations:
                    story.extend(
                        labeled_paragraph("Evidence:", citation, "evidence")
                        for citation in detail.evidence_citations
                    )
                story.append(Spacer(1, 10))
        else:
            story.append(paragraph("No rubric scores available."))

        for title, items, empty_message in (
            ("Strengths", report.strengths, "No strengths available."),
            ("Weaknesses", report.weaknesses, "No weaknesses available."),
        ):
            story.extend(section_heading(title))
            if items:
                for index, item in enumerate(items, start=1):
                    story.append(paragraph(f"{index}. {item}"))
                    story.append(Spacer(1, 4))
            else:
                story.append(paragraph(empty_message))

        story.extend(section_heading("Individual Scores"))
        if report.individual_scores:
            for score in report.individual_scores:
                email = ""
                if include_student_emails and self._user_repository is not None:
                    user = self._user_repository.get_by_id(score.student_id)
                    email = f" ({user.email})" if user else ""
                student_header = Table(
                    [
                        [
                            paragraph(
                                f"Student {score.student_id}{email}: {score.score}",
                                "category",
                            )
                        ]
                    ],
                    colWidths=[content_width],
                )
                student_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), pale_neutral),
                            ("LINEBELOW", (0, 0), (-1, -1), 0.6, light_neutral),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.extend(
                    [
                        student_header,
                        Spacer(1, 5),
                        labeled_paragraph("Rationale:", score.rationale, "card"),
                        Spacer(1, 8),
                    ]
                )
        else:
            story.append(paragraph("No individual scores available."))

        story.extend(section_heading("Recommendations"))
        if report.recommendations:
            for index, recommendation in enumerate(report.recommendations, start=1):
                story.append(paragraph(f"{index}. {recommendation}"))
                story.append(Spacer(1, 4))
        else:
            story.append(paragraph("No recommendations available."))

        document = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=left_margin,
            rightMargin=right_margin,
            topMargin=54,
            bottomMargin=58,
            title="SprintSight Assessment Report",
            author="SprintSight",
        )
        document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
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
        writer.writerow(["Rationale", report.team_score.rationale])
        writer.writerow([])

        # Rubric breakdown.
        writer.writerow(["Rubric Breakdown"])
        writer.writerow(["Dimension", "Score", "Justification", "Evidence"])
        if report.rubric_scores:
            for dimension, detail in report.rubric_scores.items():
                evidence = ",\n    ".join(detail.evidence_citations)
                writer.writerow([dimension, detail.score, detail.justification or "", evidence])
        else:
            writer.writerow(["No rubric scores available", "", "", ""])
        writer.writerow([])

        # Strengths and weaknesses.
        writer.writerow(["Strengths"])
        if report.strengths:
            for strength in report.strengths:
                writer.writerow([strength])
        else:
            writer.writerow(["No strengths available"])
        writer.writerow([])

        writer.writerow(["Weaknesses"])
        if report.weaknesses:
            for weakness in report.weaknesses:
                writer.writerow([weakness])
        else:
            writer.writerow(["No weaknesses available"])
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

        return buffer.getvalue().encode("utf-8-sig")


class RateLimitError(Exception):
    """Raised when the export rate limit is exceeded."""


# In-memory store for generated export files keyed by download token.
# In production this would be backed by object storage (e.g. MinIO/S3) with TTL.
_EXPORT_STORE: dict[str, tuple[bytes, datetime, ExportFormat]] = {}
