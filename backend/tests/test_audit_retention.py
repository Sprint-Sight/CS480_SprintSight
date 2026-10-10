import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.repositories.in_memory import InMemoryActionAuditRepository, InMemoryAuditRepository
from app.schemas.assessment import ActionAuditRecord, AuditRecord
from app.services.auditLogService.archive_reader import read_archived_month
from app.services.auditLogService.legacy_import import import_legacy_audit_file
from app.services.auditLogService.retention import AuditRetentionJob
from app.services.auditLogService.service import append_action_audit


class FakeArchiveStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.fail_upload = False
        self.corrupt_head = False

    def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        mime_type: str,
        metadata: dict[str, str] | None = None,
    ) -> str:
        if self.fail_upload:
            raise RuntimeError("MinIO unavailable")
        self.objects[(bucket, key)] = data
        self.metadata[(bucket, key)] = metadata or {}
        return key

    def download(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]

    def head(self, bucket: str, key: str) -> dict:
        data = self.objects[(bucket, key)]
        return {
            "ContentLength": len(data) + int(self.corrupt_head),
            "Metadata": self.metadata[(bucket, key)],
        }

    def list(self, bucket: str, prefix: str = "") -> list[dict[str, str]]:
        return [
            {"Key": key}
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        ]

    def delete(self, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)
        self.metadata.pop((bucket, key), None)


def _action(audit_id: str, created_at: datetime) -> ActionAuditRecord:
    return ActionAuditRecord(
        audit_id=audit_id,
        actor_id="instructor-1",
        actor_role="instructor",
        action="create_course",
        target_type="course",
        target_id="course-1",
        created_at=created_at,
    )


def _override(override_id: str, timestamp: datetime) -> AuditRecord:
    return AuditRecord(
        override_id=override_id,
        timestamp=timestamp,
        instructor_id="instructor-1",
        student_id="student-1",
        report_id="report-1",
        original_score=70,
        new_score=80,
        reason_comment="Corrected after review.",
    )


def _job(actions, overrides, storage, **kwargs) -> AuditRetentionJob:
    return AuditRetentionJob(
        actions,
        overrides,
        archive_storage=storage,
        bucket="audit-archive-test",
        hot_retention_days=168,
        action_archive_retention_days=365,
        override_archive_retention_days=365,
        batch_size=10,
        **kwargs,
    )


def test_retention_archives_old_rows_and_expires_categories_separately() -> None:
    now = datetime(2026, 10, 5, tzinfo=UTC)
    actions = InMemoryActionAuditRepository()
    overrides = InMemoryAuditRepository()
    archive = FakeArchiveStorage()
    actions.save_action_audit(_action("old-action", now - timedelta(days=169)))
    actions.save_action_audit(_action("recent-action", now - timedelta(days=1)))
    overrides.save_audit(_override("old-override", now - timedelta(days=200)))

    result = _job(actions, overrides, archive).run(now)

    assert result.action_records_archived == 1
    assert result.override_records_archived == 1
    assert [record.audit_id for record in actions.list_action_audits()] == ["recent-action"]
    assert overrides.list_audits() == []
    action_key = next(
        key
        for _, key in archive.objects
        if key.endswith(".ndjson.gz") and key.startswith("actions/")
    )
    archived_action = json.loads(
        gzip.decompress(archive.download("audit-archive-test", action_key))
    )
    assert archived_action["audit_id"] == "old-action"
    action_manifest_key = f"{action_key}.manifest.json"
    action_manifest = json.loads(archive.download("audit-archive-test", action_manifest_key))
    action_head = archive.head("audit-archive-test", action_key)
    assert action_manifest["record_count"] == 1
    assert action_manifest["compressed_size_bytes"] == action_head["ContentLength"]
    assert action_head["Metadata"]["record-count"] == "1"
    assert action_head["Metadata"]["sha256-uncompressed"] == action_manifest["sha256_uncompressed"]
    restored = read_archived_month(
        "actions",
        action_manifest["first_event_at"][:7],
        archive,
        "audit-archive-test",
    )
    assert [record.audit_id for record in restored] == ["old-action"]

    later = _job(actions, overrides, archive).run(now + timedelta(days=366))
    assert later.action_archives_deleted == 1
    assert later.override_archives_deleted == 1
    assert ("audit-archive-test", action_key) not in archive.objects
    remaining_action_key = next(
        key
        for _, key in archive.objects
        if key.endswith(".ndjson.gz") and key.startswith("actions/")
    )
    remaining_action = json.loads(
        gzip.decompress(archive.download("audit-archive-test", remaining_action_key))
    )
    assert remaining_action["audit_id"] == "recent-action"
    assert not any(key.startswith("overrides/") for _, key in archive.objects)


def test_retention_does_not_delete_rows_when_archive_upload_fails() -> None:
    now = datetime(2026, 10, 5, tzinfo=UTC)
    actions = InMemoryActionAuditRepository()
    overrides = InMemoryAuditRepository()
    archive = FakeArchiveStorage()
    actions.save_action_audit(_action("old-action", now - timedelta(days=169)))
    archive.fail_upload = True

    with pytest.raises(RuntimeError, match="MinIO unavailable"):
        _job(actions, overrides, archive).run(now)

    assert [record.audit_id for record in actions.list_action_audits()] == ["old-action"]
    assert archive.objects == {}


def test_retention_does_not_delete_rows_when_archive_size_verification_fails() -> None:
    now = datetime(2026, 10, 5, tzinfo=UTC)
    actions = InMemoryActionAuditRepository()
    overrides = InMemoryAuditRepository()
    archive = FakeArchiveStorage()
    actions.save_action_audit(_action("old-action", now - timedelta(days=169)))
    archive.corrupt_head = True

    with pytest.raises(RuntimeError, match="size verification failed"):
        _job(actions, overrides, archive).run(now)

    assert [record.audit_id for record in actions.list_action_audits()] == ["old-action"]


def test_daily_batches_in_same_month_write_distinct_objects() -> None:
    now = datetime(2026, 10, 5, tzinfo=UTC)
    actions = InMemoryActionAuditRepository()
    overrides = InMemoryAuditRepository()
    archive = FakeArchiveStorage()
    first_event = now - timedelta(days=200)
    for index in range(11):
        actions.save_action_audit(
            _action(f"old-action-{index:02d}", first_event + timedelta(minutes=index))
        )

    result = _job(actions, overrides, archive).run(now)

    objects = [
        key
        for _, key in archive.objects
        if key.startswith("actions/") and key.endswith(".ndjson.gz")
    ]
    manifests = [
        json.loads(archive.download("audit-archive-test", f"{key}.manifest.json"))
        for key in objects
    ]
    assert result.action_records_archived == 11
    assert len(objects) == 2
    assert len(set(objects)) == 2
    assert sorted(manifest["record_count"] for manifest in manifests) == [1, 10]


def test_legacy_import_is_idempotent_and_preserves_invalid_source_lines(tmp_path) -> None:
    actions = InMemoryActionAuditRepository()
    overrides = InMemoryAuditRepository()
    source = tmp_path / "audit.log"
    legacy_action = _action("legacy-action", datetime(2026, 1, 1, tzinfo=UTC)).model_dump(
        mode="json"
    )
    legacy_action.pop("audit_id")
    source_text = (
        _action("legacy-action", datetime(2026, 1, 1, tzinfo=UTC)).model_dump_json()
        + "\n"
        + json.dumps(legacy_action)
        + "\n"
        + _override("legacy-override", datetime(2026, 1, 2, tzinfo=UTC)).model_dump_json()
        + "\nnot valid json\n"
    )
    source.write_text(source_text, encoding="utf-8")

    first = import_legacy_audit_file(source, actions, overrides)
    second = import_legacy_audit_file(source, actions, overrides)

    assert first.action_records_processed == 2
    assert first.override_records_processed == 1
    assert first.invalid_line_numbers == [4]
    assert second.invalid_line_numbers == [4]
    assert len(actions.list_action_audits()) == 2
    assert len(overrides.list_audits()) == 1
    assert source.read_text(encoding="utf-8") == source_text
    generated_ids = {
        record.audit_id
        for record in actions.list_action_audits()
        if record.audit_id.startswith("legacy-import-")
    }
    assert len(generated_ids) == 1
    assert len(actions.list_action_audits()) == 2


def test_action_audit_sanitizes_sensitive_detail_keys() -> None:
    repository = InMemoryActionAuditRepository()

    record = append_action_audit(
        repository,
        actor_id="instructor-1",
        actor_role="instructor",
        action="update_user",
        target_type="user",
        target_id="student-1",
        details={
            "email": "student@example.edu",
            "password": "must-not-persist",
            "jira_api_token": "must-not-persist",
            "nested": {"authorization": "must-not-persist", "safe": "kept"},
            "items": [{"client_secret": "must-not-persist", "count": 2}],
        },
    )

    assert record.details == {
        "email": "student@example.edu",
        "nested": {"safe": "kept"},
        "items": [{"count": 2}],
    }
