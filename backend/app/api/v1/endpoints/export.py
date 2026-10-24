"""Export endpoints for downloading assessment reports as PDF or CSV."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.dependencies.auth import (
    get_action_audit_repository,
    get_assessment_repository,
    get_export_log_repository,
    get_project_repository,
    get_user_repository,
    require_faculty,
)
from app.repositories.interfaces import (
    ActionAuditRepository,
    AssessmentRepository,
    ExportLogRepository,
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.auth import Role
from app.schemas.export import (
    ExportFormat,
    ExportPreviewResponse,
    ExportRequest,
    ExportResponse,
)
from app.services.exportService.service import (
    _EXPORT_STORE,
    ExportService,
    RateLimitError,
)

router = APIRouter(tags=["exports"])


def _require_course_instructor(
    current_user: UserRecord,
    course_id: str,
    project_repository: ProjectRepository,
) -> None:
    """Verify the requesting instructor teaches (is assigned to) the course.

    Admins are exempt from the course-assignment check.
    """
    if current_user.role not in (Role.INSTRUCTOR, Role.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors or admins can export assessment reports.",
        )
    if current_user.role == Role.ADMIN:
        return
    if not project_repository.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to teach this course.",
        )


# ------------------------------------------------------------------
# GET /export/preview
# ------------------------------------------------------------------

@router.get("/preview", response_model=ExportPreviewResponse)
def export_preview(
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    course_id: str = Query(..., description="Course offering ID."),
    project_id: str = Query(..., description="Project group ID."),
    sprint_id: str = Query(..., description="Sprint identifier."),
) -> ExportPreviewResponse:
    """Fetch basic assessment data for the UI preview before export.

    Verifies the requesting instructor teaches the course.
    """
    _require_course_instructor(current_user, course_id, projects)

    if assessment_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Assessment repository unavailable.",
        )

    reports = assessment_repository.list_reports(course_id, project_id, sprint_id)
    if not reports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment report found for this course, project, and sprint.",
        )

    report = reports[0]
    return ExportPreviewResponse(
        report_id=report.report_id,
        course_id=report.course_id,
        project_id=report.project_id,
        sprint_id=report.sprint_id,
        generated_at=report.generated_at,
        team_score=report.team_score.score,
        team_grade=report.team_score.overall_grade or "N/A",
        student_count=len(report.individual_scores),
        recommendation_count=len(report.recommendations),
        strengths_count=len(report.strengths),
        weaknesses_count=len(report.weaknesses),
    )


# ------------------------------------------------------------------
# POST /export/pdf
# ------------------------------------------------------------------

@router.post("/pdf", response_model=ExportResponse)
def export_pdf(
    request: ExportRequest,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    export_logs: Annotated[ExportLogRepository, Depends(get_export_log_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> ExportResponse:
    """Generate a PDF assessment report and return a download URL.

    The download link expires after 1 hour. Student emails are only
    included when `include_student_emails` is explicitly true.
    """
    _require_course_instructor(current_user, request.course_id, projects)

    if request.format != ExportFormat.PDF:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format for this endpoint.",
        )

    service = ExportService(
        export_log_repository=export_logs,
        assessment_repository=assessment_repository,
        project_repository=projects,
        user_repository=users,
    )
    try:
        return service.generate_export(
            request=request,
            current_user_id=current_user.id,
            action_audits=action_audits,
        )
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ------------------------------------------------------------------
# POST /export/csv
# ------------------------------------------------------------------

@router.post("/csv", response_model=ExportResponse)
def export_csv(
    request: ExportRequest,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    export_logs: Annotated[ExportLogRepository, Depends(get_export_log_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> ExportResponse:
    """Generate a CSV assessment report and return a download URL.

    The download link expires after 1 hour. Student emails are only
    included when `include_student_emails` is explicitly true.
    """
    _require_course_instructor(current_user, request.course_id, projects)

    if request.format != ExportFormat.CSV:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format for this endpoint.",
        )

    service = ExportService(
        export_log_repository=export_logs,
        assessment_repository=assessment_repository,
        project_repository=projects,
        user_repository=users,
    )
    try:
        return service.generate_export(
            request=request,
            current_user_id=current_user.id,
            action_audits=action_audits,
        )
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ------------------------------------------------------------------
# GET /export/download/{token}
# ------------------------------------------------------------------

@router.get("/download/{download_token}")
def export_download(
    download_token: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    export_logs: Annotated[ExportLogRepository, Depends(get_export_log_repository)],
) -> StreamingResponse:
    """Download a previously generated export file.

    Links expire after 1 hour. Only the instructor who created the export
    (or an admin) may download it.
    """
    log = export_logs.get_log(download_token)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export download link not found or has expired.",
        )

    # Only the creator or an admin may download.
    if current_user.role != Role.ADMIN and log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to download this export.",
        )

    # Check expiry.
    if datetime.now(UTC) > log.expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This download link has expired.",
        )

    entry = _EXPORT_STORE.get(download_token)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Export file is no longer available.",
        )

    file_bytes, expires_at, fmt = entry
    media_type = (
        "application/pdf" if fmt == ExportFormat.PDF else "text/csv"
    )
    filename = f"sprintsight_report_{log.course_id}_{log.project_id}_{log.sprint_id}.{fmt.value}"

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Expires-At": expires_at.isoformat(),
        },
    )
