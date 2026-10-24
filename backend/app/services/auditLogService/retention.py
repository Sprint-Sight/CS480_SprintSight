import argparse
import gzip
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO

from app.core.config import get_settings
from app.core.storage import storage
from app.repositories.interfaces import ActionAuditRepository, AuditRepository
from app.repositories.postgres import (
    PostgresActionAuditRepository,
    PostgresAuditRepository,
    PostgresAuditRetentionConfigRepository,
    create_user_pool,
    ensure_audit_schema,
    ensure_audit_retention_config_schema,
)

logger = logging.getLogger(__name__)
_RETENTION_ADVISORY_LOCK_ID = 480480


@dataclass
class RetentionResult:
    action_records_archived: int = 0
    override_records_archived: int = 0
    action_archives_deleted: int = 0
    override_archives_deleted: int = 0


class AuditRetentionJob:
    def __init__(
        self,
        actions: ActionAuditRepository,
        overrides: AuditRepository,
        archive_storage=storage,
        bucket: str | None = None,
        hot_retention_days: int | None = None,
        action_archive_retention_days: int | None = None,
        override_archive_retention_days: int | None = None,
        batch_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.actions = actions
        self.overrides = overrides
        self.archive_storage = archive_storage
        self.bucket = bucket or settings.minio_bucket_audit_archive
        self.hot_retention_days = hot_retention_days or settings.audit_hot_retention_days
        self.action_archive_retention_days = (
            action_archive_retention_days or settings.audit_action_archive_retention_days
        )
        self.override_archive_retention_days = (
            override_archive_retention_days or settings.audit_override_archive_retention_days
        )
        self.batch_size = batch_size or settings.audit_archive_batch_size

    def run(self, now: datetime | None = None) -> RetentionResult:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Retention run timestamp must be timezone-aware.")
        cutoff = now.astimezone(UTC) - timedelta(days=self.hot_retention_days)
        result = RetentionResult()
        result.action_records_archived = self._archive_rows(
            "actions",
            self.actions,
            cutoff,
            self.action_archive_retention_days,
            "audit_id",
            "created_at",
            now,
        )
        result.override_records_archived = self._archive_rows(
            "overrides",
            self.overrides,
            cutoff,
            self.override_archive_retention_days,
            "override_id",
            "timestamp",
            now,
        )
        result.action_archives_deleted = self._delete_expired_archives("actions", now)
        result.override_archives_deleted = self._delete_expired_archives("overrides", now)
        return result

    def _archive_rows(
        self, category, repository, cutoff, archive_days, id_field, timestamp_field, archived_at
    ) -> int:
        archived = 0
        while True:
            candidates = (
                repository.list_action_audits_before(cutoff, self.batch_size)
                if category == "actions"
                else repository.list_audits_before(cutoff, self.batch_size)
            )
            if not candidates:
                return archived
            first_time = getattr(candidates[0], timestamp_field).astimezone(UTC)
            records = [
                record
                for record in candidates
                if getattr(record, timestamp_field).astimezone(UTC).strftime("%Y/%m")
                == first_time.strftime("%Y/%m")
            ]

            lines = [record.model_dump_json() for record in records]
            if len(lines) != len(records):
                raise RuntimeError(f"Audit archive row count mismatch before upload: {category}")
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            checksum = hashlib.sha256(payload).hexdigest()
            timestamps = [getattr(record, timestamp_field).astimezone(UTC) for record in records]
            first_timestamp = min(timestamps)
            last_timestamp = max(timestamps)
            archived_at = archived_at.astimezone(UTC)
            object_key = (
                f"{category}/{first_timestamp:%Y/%m}/"
                f"{first_timestamp:%Y%m%dT%H%M%SZ}-{last_timestamp:%Y%m%dT%H%M%SZ}-{checksum[:16]}.ndjson.gz"
            )
            manifest_key = f"{object_key}.manifest.json"
            compressed = self._gzip(payload)
            compressed_checksum = hashlib.sha256(compressed).hexdigest()
            object_metadata = {
                "sha256-uncompressed": checksum,
                "sha256-gzip": compressed_checksum,
                "record-count": str(len(records)),
                "compressed-size-bytes": str(len(compressed)),
                "uncompressed-size-bytes": str(len(payload)),
            }
            manifest = {
                "schema_version": 1,
                "category": category,
                "object_key": object_key,
                "record_count": len(records),
                "uncompressed_size_bytes": len(payload),
                "compressed_size_bytes": len(compressed),
                "first_event_at": first_timestamp.isoformat(),
                "last_event_at": last_timestamp.isoformat(),
                "archived_at": archived_at.isoformat(),
                "expires_at": (archived_at + timedelta(days=archive_days)).isoformat(),
                "sha256_uncompressed": checksum,
                "sha256_gzip": compressed_checksum,
            }
            self.archive_storage.upload(
                self.bucket,
                object_key,
                compressed,
                "application/gzip",
                object_metadata,
            )
            object_head = self.archive_storage.head(self.bucket, object_key)
            if object_head.get("ContentLength") != len(compressed):
                raise RuntimeError(f"Audit archive size verification failed: {object_key}")
            if object_head.get("Metadata", {}) != object_metadata:
                raise RuntimeError(f"Audit archive metadata verification failed: {object_key}")
            archived_payload = self.archive_storage.download(self.bucket, object_key)
            if len(archived_payload) != len(compressed):
                raise RuntimeError(f"Audit archive read-back size mismatch: {object_key}")
            if hashlib.sha256(archived_payload).hexdigest() != compressed_checksum:
                raise RuntimeError(f"Audit archive compressed checksum mismatch: {object_key}")
            uncompressed_payload = gzip.decompress(archived_payload)
            if hashlib.sha256(uncompressed_payload).hexdigest() != checksum:
                raise RuntimeError(f"Audit archive checksum verification failed: {object_key}")
            archived_lines = uncompressed_payload.splitlines()
            if len(archived_lines) != len(records):
                raise RuntimeError(f"Audit archive row count verification failed: {object_key}")
            for line in archived_lines:
                json.loads(line)

            manifest_payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
            self.archive_storage.upload(
                self.bucket, manifest_key, manifest_payload, "application/json"
            )
            if self.archive_storage.download(self.bucket, manifest_key) != manifest_payload:
                raise RuntimeError(f"Audit archive manifest verification failed: {manifest_key}")

            ids = [str(getattr(record, id_field)) for record in records]
            deleted = (
                repository.delete_action_audits(ids)
                if category == "actions"
                else repository.delete_audits(ids)
            )
            if deleted != len(records):
                raise RuntimeError(
                    f"Expected to delete {len(records)} archived {category} rows, "
                    f"deleted {deleted}."
                )
            archived += deleted

    @staticmethod
    def _gzip(payload: bytes) -> bytes:
        output = BytesIO()
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as compressed:
            compressed.write(payload)
        return output.getvalue()

    def _delete_expired_archives(self, category: str, now: datetime) -> int:
        deleted = 0
        for item in self.archive_storage.list(self.bucket, f"{category}/"):
            key = item["Key"]
            if not key.endswith(".manifest.json"):
                continue
            manifest = json.loads(self.archive_storage.download(self.bucket, key))
            expires_at = datetime.fromisoformat(manifest["expires_at"])
            if expires_at.tzinfo is None:
                raise ValueError(f"Archive manifest has no timezone: {key}")
            if expires_at.astimezone(UTC) > now.astimezone(UTC):
                continue
            self.archive_storage.delete(self.bucket, manifest["object_key"])
            self.archive_storage.delete(self.bucket, key)
            deleted += 1
        return deleted


def run_once() -> RetentionResult:
    settings = get_settings()
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    try:
        ensure_audit_schema(pool)
        ensure_audit_retention_config_schema(
            pool,
            settings.audit_hot_retention_days,
            settings.audit_action_archive_retention_days,
            settings.audit_override_archive_retention_days,
        )
        storage.init_buckets()
        config = PostgresAuditRetentionConfigRepository(pool).get_config()
        job = AuditRetentionJob(
            PostgresActionAuditRepository(pool),
            PostgresAuditRepository(pool),
            hot_retention_days=config.hot_retention_days,
            action_archive_retention_days=config.action_archive_retention_days,
            override_archive_retention_days=config.override_archive_retention_days,
        )
        with pool.connection() as lock_connection:
            with lock_connection.transaction():
                lock_row = lock_connection.execute(
                    "SELECT pg_try_advisory_xact_lock(%s) AS locked",
                    (_RETENTION_ADVISORY_LOCK_ID,),
                ).fetchone()
                if not lock_row["locked"]:
                    logger.info("Another audit retention run is active; skipping this run.")
                    return RetentionResult()
                result = job.run()
        print(json.dumps(asdict(result), sort_keys=True))
        return result
    except Exception:
        logger.exception("Audit retention job failed.")
        raise
    finally:
        pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive and expire audit records.")
    parser.add_argument("--loop", action="store_true", help="Run immediately, then repeat daily.")
    parser.add_argument("--interval-seconds", type=int, default=86400)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            run_once()
        except Exception:
            if not args.loop:
                raise
        if not args.loop:
            return
        time.sleep(max(args.interval_seconds, 60))


if __name__ == "__main__":
    main()
