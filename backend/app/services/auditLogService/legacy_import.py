import argparse
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.repositories.interfaces import ActionAuditRepository, AuditRepository
from app.repositories.postgres import (
    PostgresActionAuditRepository,
    PostgresAuditRepository,
    create_user_pool,
    ensure_audit_schema,
)
from app.schemas.assessment import ActionAuditRecord, AuditRecord

logger = logging.getLogger(__name__)


def _legacy_record_id(category: str, payload: dict) -> str:
    canonical = json.dumps(
        {"category": category, "record": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"legacy-import-{hashlib.sha256(canonical).hexdigest()}"


@dataclass
class ImportResult:
    action_records_processed: int = 0
    override_records_processed: int = 0
    invalid_line_numbers: list[int] = field(default_factory=list)


def import_legacy_audit_file(
    path: Path,
    actions: ActionAuditRepository,
    overrides: AuditRepository,
) -> ImportResult:
    result = ImportResult()
    if not path.exists():
        return result

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Audit event must be a JSON object")
                if "audit_id" in payload or "actor_id" in payload:
                    if not payload.get("audit_id"):
                        record_payload = {
                            key: value for key, value in payload.items() if key != "audit_id"
                        }
                        payload["audit_id"] = _legacy_record_id("actions", record_payload)
                    record = ActionAuditRecord.model_validate(payload)
                elif "override_id" in payload or "instructor_id" in payload:
                    if not payload.get("override_id"):
                        record_payload = {
                            key: value for key, value in payload.items() if key != "override_id"
                        }
                        payload["override_id"] = _legacy_record_id("overrides", record_payload)
                    record = AuditRecord.model_validate(payload)
                else:
                    raise ValueError("Unrecognized audit event shape")
            except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
                result.invalid_line_numbers.append(line_number)
                continue

            if isinstance(record, ActionAuditRecord):
                actions.save_action_audit(record)
                result.action_records_processed += 1
            else:
                overrides.save_audit(record)
                result.override_records_processed += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import legacy JSONL audit events into PostgreSQL."
    )
    parser.add_argument("path", nargs="?", type=Path, default=Path(get_settings().audit_log_path))
    args = parser.parse_args()
    settings = get_settings()
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    try:
        ensure_audit_schema(pool)
        result = import_legacy_audit_file(
            args.path,
            PostgresActionAuditRepository(pool),
            PostgresAuditRepository(pool),
        )
    finally:
        pool.close()

    print(json.dumps(asdict(result), sort_keys=True))
    if result.invalid_line_numbers:
        logger.error(
            "Invalid audit JSONL lines were left in the source file: %s",
            result.invalid_line_numbers,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
