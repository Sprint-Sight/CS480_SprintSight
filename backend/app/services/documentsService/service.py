from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePath
from typing import Protocol
from uuid import uuid4

from app.core.config import Settings
from app.repositories.interfaces import DocumentRecord, DocumentRepository


class DocumentStorage(Protocol):
    def upload(self, bucket: str, key: str, data: bytes, mime_type: str = "application/octet-stream") -> str: ...

    def download(self, bucket: str, key: str) -> bytes: ...

    def delete(self, bucket: str, key: str) -> None: ...


class DocumentValidationError(ValueError):
    pass


def upload_documents(
    project_id: str,
    uploader_id: str,
    files: list[tuple[str, str | None, bytes]],
    repository: DocumentRepository,
    storage: DocumentStorage,
    settings: Settings,
) -> list[DocumentRecord]:
    if not files:
        raise DocumentValidationError("At least one PDF document is required.")
    if sum(len(content) for _, _, content in files) > settings.document_max_request_size:
        raise DocumentValidationError("The total upload size exceeds the request limit.")

    created: list[DocumentRecord] = []
    uploaded_keys: list[tuple[str, str]] = []
    try:
        for filename, content_type, content in files:
            if not content or len(content) > settings.document_max_file_size:
                raise DocumentValidationError("Each PDF must be non-empty and within the file size limit.")
            if content_type != "application/pdf" or not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
                raise DocumentValidationError("Only valid PDF documents are accepted.")
            document_id = str(uuid4())
            safe_filename = PurePath(filename).name or f"{document_id}.pdf"
            storage_key = f"projects/{project_id}/documents/{document_id}/{safe_filename}"
            storage.upload(settings.minio_bucket_documents, storage_key, content, "application/pdf")
            uploaded_keys.append((settings.minio_bucket_documents, storage_key))
            record = DocumentRecord(
                id=document_id,
                project_id=project_id,
                filename=safe_filename,
                mime_type="application/pdf",
                byte_size=len(content),
                checksum=sha256(content).hexdigest(),
                storage_bucket=settings.minio_bucket_documents,
                storage_key=storage_key,
                uploaded_by=uploader_id,
                created_at=datetime.now(timezone.utc),
            )
            created.append(repository.create_document(record))
    except Exception:
        for bucket, key in reversed(uploaded_keys):
            try:
                storage.delete(bucket, key)
            except Exception:
                pass
        raise
    return created


def collect_document_signals(payload) -> dict[str, float]:
    return {
        "documentation_quality": 82.0,
        "demo_completeness": 78.0,
    }
