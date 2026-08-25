from pathlib import Path

from app.core.config import get_settings
from app.repositories.in_memory import audit_repo
from app.schemas.assessment import AuditRecord, OverrideResponse


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

    audit_log_path = Path(get_settings().audit_log_path)
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(audit.model_dump_json() + "\n")

    return audit


def list_audit_records() -> list[AuditRecord]:
    return audit_repo.list_audits()
