from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import (
    get_action_audit_repository,
    get_audit_repository,
    get_audit_retention_config_repository,
    require_admin,
    require_faculty,
)
from app.repositories.interfaces import (
    ActionAuditRepository,
    AuditRepository,
    AuditRetentionConfigRepository,
    UserRecord,
)
from app.schemas.audit import AuditRetentionConfigResponse, AuditRetentionConfigUpdate
from app.services.auditLogService.service import (
    append_action_audit,
    list_action_audit_records,
    list_audit_records,
)

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


@router.get("/retention", response_model=AuditRetentionConfigResponse)
def get_audit_retention_config(
    _: Annotated[UserRecord, Depends(require_admin)],
    repository: Annotated[AuditRetentionConfigRepository, Depends(get_audit_retention_config_repository)],
) -> AuditRetentionConfigResponse:
    return repository.get_config()


@router.put("/retention", response_model=AuditRetentionConfigResponse)
def update_audit_retention_config(
    payload: AuditRetentionConfigUpdate,
    current_user: Annotated[UserRecord, Depends(require_admin)],
    repository: Annotated[AuditRetentionConfigRepository, Depends(get_audit_retention_config_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> AuditRetentionConfigResponse:
    updated = repository.update_config(
        hot_retention_days=payload.hot_retention_days,
        action_archive_retention_days=payload.action_archive_retention_days,
        override_archive_retention_days=payload.override_archive_retention_days,
        updated_by=current_user.id,
    )
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="update_audit_retention",
        target_type="audit_retention_config",
        target_id="global",
        details=payload.model_dump(),
    )
    return updated
