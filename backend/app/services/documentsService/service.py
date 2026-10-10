import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePath
from typing import Protocol
from uuid import uuid4

from app.core.config import Settings
from app.repositories.interfaces import DocumentRecord, DocumentRepository

log = logging.getLogger(__name__)


class DocumentStorage(Protocol):
    def upload(self, bucket: str, key: str, data: bytes, mime_type: str = "application/octet-stream") -> str: ...

    def download(self, bucket: str, key: str) -> bytes: ...

    def delete(self, bucket: str, key: str) -> None: ...


class DocumentValidationError(ValueError):
    pass


SUPPORTED_DOCUMENT_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK"),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", b"PK"),
}


def upload_documents(
    project_id: str,
    uploader_id: str,
    files: list[tuple[str, str | None, bytes]],
    repository: DocumentRepository,
    storage: DocumentStorage,
    settings: Settings,
) -> list[DocumentRecord]:
    if not files:
        raise DocumentValidationError("At least one document is required.")
    if sum(len(content) for _, _, content in files) > settings.document_max_request_size:
        raise DocumentValidationError("The total upload size exceeds the request limit.")

    created: list[DocumentRecord] = []
    uploaded_keys: list[tuple[str, str]] = []
    try:
        for filename, content_type, content in files:
            if not content or len(content) > settings.document_max_file_size:
                raise DocumentValidationError("Each document must be non-empty and within the file size limit.")
            extension = PurePath(filename).suffix.lower()
            document_type = SUPPORTED_DOCUMENT_TYPES.get(extension)
            if not document_type or content_type != document_type[0] or not content.startswith(document_type[1]):
                raise DocumentValidationError("Only valid PDF, DOCX, and PPTX documents are accepted.")
            document_id = str(uuid4())
            safe_filename = PurePath(filename).name or f"{document_id}{extension}"
            storage_key = f"projects/{project_id}/documents/{document_id}/{safe_filename}"
            storage.upload(settings.minio_bucket_documents, storage_key, content, document_type[0])
            uploaded_keys.append((settings.minio_bucket_documents, storage_key))
            record = DocumentRecord(
                id=document_id,
                project_id=project_id,
                filename=safe_filename,
                mime_type=document_type[0],
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


# Word's main document body lives at word/document.xml; <w:t> elements hold the
# visible text runs, and <w:p> elements separate paragraphs. We walk the tree
# with ElementTree rather than pulling in python-docx so there's no new
# dependency to deploy for a parser that only needs plain-text output.
_WORDPROCESSINGML_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            with archive.open("word/document.xml") as document_xml:
                tree = ET.parse(document_xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        log.warning("Failed to parse .docx for AI context: %s", exc)
        return ""

    paragraphs: list[str] = []
    for paragraph in tree.getroot().iter(f"{_WORDPROCESSINGML_NAMESPACE}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{_WORDPROCESSINGML_NAMESPACE}t")]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


# Legacy .doc (OLE compound binary) parsing without a C extension is lossy. We
# strip to printable ASCII runs of at least four characters as a best-effort
# fallback so faculty-provided .doc files aren't silently dropped from the
# LLM's context. Teams who want full fidelity should re-save as .docx.
_PRINTABLE_RUN = re.compile(rb"[\x20-\x7E\r\n\t]{4,}")


def _extract_doc_text(content: bytes) -> str:
    runs = _PRINTABLE_RUN.findall(content)
    if not runs:
        return ""
    text = "\n".join(run.decode("ascii", errors="ignore") for run in runs)
    return text.strip()


def _extract_plaintext(content: bytes) -> str:
    # UTF-8 covers Markdown and most .txt. Fall back to latin-1 (never raises)
    # before dropping any content; the LLM tolerates a little garbled text
    # better than an empty context block.
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _extract_pdf_text(content: bytes) -> str:
    """Pull plain text out of a PDF with pdfplumber.

    Imported lazily so the module still imports (for tests, scripts, etc.)
    on environments where pdfplumber isn't installed; the AI engine already
    ships with pdfplumber in its container, and the backend declares it in
    pyproject.toml for production deployments.
    """
    try:
        import pdfplumber  # noqa: PLC0415 - lazy import, see docstring above
    except ImportError:
        log.warning(
            "pdfplumber is not installed; cannot extract text from uploaded PDF. "
            "Install it to feed PDF documents to the AI engine as background context."
        )
        return ""

    try:
        pages_text: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    pages_text.append(f"[Page {index}]\n{page_text}")
        return "\n\n".join(pages_text)
    except Exception as exc:
        log.warning("Failed to extract text from PDF for AI context: %s", exc)
        return ""


def extract_document_text(record: DocumentRecord, content: bytes) -> str:
    """Return plain text extracted from a stored document, or '' if unsupported."""
    extension = PurePath(record.filename).suffix.lower()
    if extension in (".md", ".txt"):
        return _extract_plaintext(content)
    if extension == ".docx":
        return _extract_docx_text(content)
    if extension == ".doc":
        return _extract_doc_text(content)
    if extension == ".pdf":
        return _extract_pdf_text(content)
    return ""


# Hard cap on per-document extracted text, in characters. Keeps a single
# oversized upload from blowing out the LLM's context window; the dimension
# evaluator in ai-engine still re-checks the overall prompt size.
_MAX_CONTEXT_CHARS_PER_DOCUMENT = 50_000


def collect_project_context_documents(
    project_id: str,
    repository: DocumentRepository,
    storage: DocumentStorage,
) -> list[dict]:
    """Load every uploaded document for a project and return its extracted text.

    This is BACKGROUND CONTEXT for the LLM — e.g. project briefs, requirements
    documents, or design notes — distinct from the rubric's `documentation`
    dimension, which scores documentation produced by the team inside the
    repository (READMEs, docs/, changelogs, etc.). Callers must pass this
    through to the AI engine as a separate payload field so the two concepts
    stay separated in the model's prompt as well.
    """
    documents: list[dict] = []
    records = repository.list_documents(project_id)
    log.info(
        "Collecting project-context documents for project %s: %d record(s) in repository.",
        project_id, len(records),
    )
    for record in records:
        try:
            content = storage.download(record.storage_bucket, record.storage_key)
        except Exception as exc:
            log.warning(
                "Skipping project-context document %s/%s (filename=%s, download failed): %s",
                project_id, record.id, record.filename, exc,
            )
            continue
        text = extract_document_text(record, content)
        if not text:
            # PDFs and files we failed to parse are deliberately omitted here —
            # we don't want to send raw/garbled bytes as "context".
            log.info(
                "Skipping project-context document %s (mime=%s, bytes=%d): no text extracted. "
                "PDFs and unsupported types are intentionally excluded here.",
                record.filename, record.mime_type, len(content),
            )
            continue
        if len(text) > _MAX_CONTEXT_CHARS_PER_DOCUMENT:
            text = text[:_MAX_CONTEXT_CHARS_PER_DOCUMENT] + "\n...[truncated for context window]"
        log.info(
            "Including project-context document %s (mime=%s, extracted %d chars).",
            record.filename, record.mime_type, len(text),
        )
        documents.append(
            {
                "document_id": record.id,
                "filename": record.filename,
                "mime_type": record.mime_type,
                "text": text,
            }
        )
    log.info(
        "Project %s: %d of %d document(s) carried into AI context.",
        project_id, len(documents), len(records),
    )
    return documents
