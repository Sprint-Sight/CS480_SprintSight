from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_faculty
from app.schemas.assessment import AssessRequest, OverrideRequest
from app.services.assessmentService.service import (
    generate_mock_assessment,
    get_latest_assessment,
    override_student_score,
)
from app.services.auditLogService.service import append_override_audit
from app.services.documentsService.service import collect_document_signals
from app.services.gitlabGithub.service import ingest_github_metrics
from app.services.jiraService.service import enrich_jira_metrics
from app.services.manualTextService.service import get_manual_text
from app.services.middleManService.service import build_assessment_payload

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("/assess")
def assess_sprint(
    payload: AssessRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
) -> dict:
    _ = faculty_user
    metrics = ingest_github_metrics(payload)
    _ = enrich_jira_metrics(payload)
    docs = collect_document_signals(payload)
    manual_text = get_manual_text(payload.course_id, payload.project_id, payload.sprint_id)
    middle_man_payload = build_assessment_payload(metrics, docs, manual_text)

    report = generate_mock_assessment(payload)
    return {
        "input_payload": middle_man_payload,
        "report": report,
    }


@router.get("/latest")
def get_latest(
    course_id: str,
    project_id: str,
    sprint_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
):
    _ = faculty_user
    return get_latest_assessment(course_id, project_id, sprint_id)


@router.post("/override")
def override_score(
    payload: OverrideRequest,
    faculty_user: Annotated[object, Depends(require_faculty)],
):
    override_record = override_student_score(payload, instructor_id=faculty_user.id)
    audit = append_override_audit(override_record)
    return {
        "override": override_record,
        "audit": audit,
    }
