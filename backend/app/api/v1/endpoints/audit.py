from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_action_audit_repository, get_audit_repository, require_faculty
from app.repositories.interfaces import ActionAuditRepository, AuditRepository
from app.services.auditLogService.service import list_action_audit_records, list_audit_records

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/overrides")
def get_override_audits(
    faculty_user: Annotated[object, Depends(require_faculty)],
    repository: Annotated[AuditRepository, Depends(get_audit_repository)],
):
    return list_audit_records(repository, faculty_user)


@router.get("/actions")
def get_action_audits(
    faculty_user: Annotated[object, Depends(require_faculty)],
    repository: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
):
    return list_action_audit_records(repository, faculty_user)
