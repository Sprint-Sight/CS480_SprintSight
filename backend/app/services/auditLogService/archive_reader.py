import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.storage import storage
from app.schemas.assessment import ActionAuditRecord, AuditRecord


def read_archived_month(
    category: str,
    month: str,
    archive_storage=storage,
    bucket: str | None = None,
) -> list[ActionAuditRecord | AuditRecord]:
    if category not in {"actions", "overrides"}:
        raise ValueError("Category must be 'actions' or 'overrides'.")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Month must use YYYY-MM format.")
    datetime.strptime(month, "%Y-%m")
    settings = get_settings()
    bucket = bucket or settings.minio_bucket_audit_archive
    year, month_number = month.split("-")
    prefix = f"{category}/{year}/{month_number}/"
    manifests = sorted(
        item["Key"]
        for item in archive_storage.list(bucket, prefix)
        if item["Key"].endswith(".manifest.json")
    )
    records: list[ActionAuditRecord | AuditRecord] = []
    for manifest_key in manifests:
        manifest = json.loads(archive_storage.download(bucket, manifest_key))
        object_key = manifest["object_key"]
        if manifest.get("category") != category or not object_key.startswith(prefix):
            raise ValueError(f"Archive manifest points outside requested month: {manifest_key}")

        compressed = archive_storage.download(bucket, object_key)
        object_head = archive_storage.head(bucket, object_key)
        if len(compressed) != manifest["compressed_size_bytes"]:
            raise ValueError(f"Archive compressed size mismatch: {object_key}")
        if object_head.get("ContentLength") != manifest["compressed_size_bytes"]:
            raise ValueError(f"Archive stored size mismatch: {object_key}")
        metadata = object_head.get("Metadata", {})
        if metadata.get("record-count") != str(manifest["record_count"]):
            raise ValueError(f"Archive object record-count metadata mismatch: {object_key}")
        if metadata.get("compressed-size-bytes") != str(manifest["compressed_size_bytes"]):
            raise ValueError(f"Archive object compressed-size metadata mismatch: {object_key}")
        if metadata.get("uncompressed-size-bytes") != str(manifest["uncompressed_size_bytes"]):
            raise ValueError(f"Archive object uncompressed-size metadata mismatch: {object_key}")
        if metadata.get("sha256-uncompressed") != manifest["sha256_uncompressed"]:
            raise ValueError(f"Archive object checksum metadata mismatch: {object_key}")
        if metadata.get("sha256-gzip") != manifest["sha256_gzip"]:
            raise ValueError(f"Archive object compressed-checksum metadata mismatch: {object_key}")
        if hashlib.sha256(compressed).hexdigest() != manifest["sha256_gzip"]:
            raise ValueError(f"Archive compressed checksum mismatch: {object_key}")

        payload = gzip.decompress(compressed)
        if len(payload) != manifest["uncompressed_size_bytes"]:
            raise ValueError(f"Archive uncompressed size mismatch: {object_key}")
        if hashlib.sha256(payload).hexdigest() != manifest["sha256_uncompressed"]:
            raise ValueError(f"Archive uncompressed checksum mismatch: {object_key}")
        lines = payload.splitlines()
        if len(lines) != manifest["record_count"]:
            raise ValueError(f"Archive record count mismatch: {object_key}")

        model = ActionAuditRecord if category == "actions" else AuditRecord
        for line in lines:
            record = model.model_validate_json(line)
            event_time = (
                record.created_at if isinstance(record, ActionAuditRecord) else record.timestamp
            )
            if event_time.strftime("%Y-%m") != month:
                raise ValueError(f"Archive contains a record outside requested month: {object_key}")
            records.append(record)

    return sorted(
        records,
        key=lambda record: (
            record.created_at if isinstance(record, ActionAuditRecord) else record.timestamp,
            record.audit_id if isinstance(record, ActionAuditRecord) else record.override_id,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and read an archived audit month.")
    parser.add_argument("--category", choices=("actions", "overrides"), required=True)
    parser.add_argument("--month", required=True, help="Event month in YYYY-MM format.")
    parser.add_argument("--output", type=Path, help="Write restored NDJSON to this path.")
    args = parser.parse_args()
    records = read_archived_month(args.category, args.month)
    output = "".join(f"{record.model_dump_json()}\n" for record in records)
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
