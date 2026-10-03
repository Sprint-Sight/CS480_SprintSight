from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from app.core.config import get_settings
from app.repositories.in_memory import audit_action_repo, audit_repo
from app.schemas.assessment import ActionAuditRecord, AuditRecord, OverrideResponse
from app.schemas.auth import Role

T = TypeVar("T")


def _audit_log_path() -> Path:
    return Path(get_settings().audit_log_path)


def _load_persisted_records(model_type: type[T], key_field: str) -> list[T]:
    log_path = _audit_log_path()
    if not log_path.exists():
        return []

    records: list[T] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = model_type.model_validate_json(line)
            except Exception:
                continue
            records.append(record)

    merged: dict[str, T] = {}
    for record in records:
        record_key = str(getattr(record, key_field))
        merged[record_key] = record
    return list(merged.values())


def _merge_records(current: list[T], persisted: list[T], key_field: str) -> list[T]:
    merged: dict[str, T] = {}
    for record in current:
        merged[str(getattr(record, key_field))] = record
    for record in persisted:
        merged.setdefault(str(getattr(record, key_field)), record)
    return list(merged.values())


def append_override_audit(override_record: OverrideResponse) -> AuditRecord:
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
    audit_repo.save_audit(audit)

    audit_log_path = _audit_log_path()
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(audit.model_dump_json() + "\n")

    return audit


def append_action_audit(
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
        details=details or {},
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    audit_action_repo.save_action_audit(record)

    audit_log_path = _audit_log_path()
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json() + "\n")

    return record


def list_audit_records(current_user: object | None = None) -> list[AuditRecord]:
    records = _merge_records(audit_repo.list_audits(), _load_persisted_records(AuditRecord, "override_id"), "override_id")
    if current_user is None:
        return records
    if getattr(current_user, "role", None) == Role.INSTRUCTOR:
        return [record for record in records if record.instructor_id == current_user.id]
    if getattr(current_user, "role", None) == Role.ADMIN:
        return records
    return []


def list_action_audit_records(current_user: object | None = None) -> list[ActionAuditRecord]:
    records = _merge_records(
        audit_action_repo.list_action_audits(),
        _load_persisted_records(ActionAuditRecord, "audit_id"),
        "audit_id",
    )
    if current_user is None:
        return records
    if getattr(current_user, "role", None) == Role.INSTRUCTOR:
        return [record for record in records if record.actor_id == current_user.id]
    if getattr(current_user, "role", None) == Role.ADMIN:
        return records
    return []
