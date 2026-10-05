from datetime import UTC, datetime
from uuid import uuid4

from app.repositories.interfaces import ActionAuditRepository, AuditRepository
from app.schemas.assessment import ActionAuditRecord, AuditRecord, OverrideResponse
from app.schemas.auth import Role

_SENSITIVE_DETAIL_KEY_MARKERS = ("password", "token", "secret", "authorization")


def sanitize_event_details(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: sanitize_event_details(item)
            for key, item in value.items()
            if not any(marker in key.casefold() for marker in _SENSITIVE_DETAIL_KEY_MARKERS)
        }
    if isinstance(value, list):
        return [sanitize_event_details(item) for item in value]
    return value


def append_override_audit(
    override_record: OverrideResponse, repository: AuditRepository
) -> AuditRecord:
    audit = AuditRecord(
        override_id=override_record.override_id,
        timestamp=override_record.created_at,
        instructor_id=override_record.instructor_id,
        student_id=override_record.student_id,
        report_id=override_record.report_id,
        original_score=override_record.original_score,
        new_score=override_record.new_score,
        reason_comment=override_record.reason_comment,
    )
    repository.save_audit(audit)

    return audit


def append_action_audit(
    repository: ActionAuditRepository,
    actor_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    details: dict | None = None,
) -> ActionAuditRecord:
    record = ActionAuditRecord(
        audit_id=str(uuid4()),
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=sanitize_event_details(details or {}),
        created_at=datetime.now(UTC),
    )
    repository.save_action_audit(record)

    return record


def list_audit_records(
    repository: AuditRepository, current_user: object | None = None
) -> list[AuditRecord]:
    records = repository.list_audits()
    if current_user is None:
        return records
    if getattr(current_user, "role", None) == Role.INSTRUCTOR:
        return [record for record in records if record.instructor_id == current_user.id]
    if getattr(current_user, "role", None) == Role.ADMIN:
        return records
    return []


def list_action_audit_records(
    repository: ActionAuditRepository,
    current_user: object | None = None,
) -> list[ActionAuditRecord]:
    records = repository.list_action_audits()
    if current_user is None:
        return records
    if getattr(current_user, "role", None) == Role.INSTRUCTOR:
        return [record for record in records if record.actor_id == current_user.id]
    if getattr(current_user, "role", None) == Role.ADMIN:
        return records
    return []
