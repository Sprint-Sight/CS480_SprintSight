from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.storage import storage
from app.main import app
from app.repositories.interfaces import ProjectRecord


client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def setup_project(repository, member_ids: list[str] | None = None) -> None:
    repository.create_project(
        ProjectRecord(
            id="project-documents",
            project_name="Documents Project",
            team_name="Documents Team",
            description=None,
            course_id="course-documents",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=datetime.now(timezone.utc),
        ),
        member_ids or [],
    )
    repository.assign_instructor("course-documents", "u-faculty-1")


def test_upload_list_and_download_multiple_pdfs(override_user_repository, monkeypatch) -> None:
    setup_project(override_user_repository, ["u-student-1"])
    objects: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "upload", lambda bucket, key, data, mime_type: objects.setdefault(key, data) and key)
    monkeypatch.setattr(storage, "download", lambda bucket, key: objects[key])
    monkeypatch.setattr(storage, "delete", lambda bucket, key: objects.pop(key, None))
    headers = {"Authorization": f"Bearer {token('student@sprintsight.edu')}"}
    files = [
        ("files", ("proposal.pdf", b"%PDF-1.7 proposal", "application/pdf")),
        ("files", ("final.pdf", b"%PDF-1.7 final", "application/pdf")),
    ]

    upload = client.post("/api/v1/projects/project-documents/documents", files=files, headers=headers)
    assert upload.status_code == 201
    records = upload.json()["documents"]
    assert len(records) == 2
    assert {record["filename"] for record in records} == {"proposal.pdf", "final.pdf"}
    assert len({record["id"] for record in records}) == 2
    assert all(record["project_id"] == "project-documents" for record in records)

    listing = client.get("/api/v1/projects/project-documents/documents", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 2
    download = client.get(
        f"/api/v1/projects/project-documents/documents/{records[0]['id']}", headers=headers
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == b"%PDF-1.7 proposal"
    assert get_settings().minio_bucket_documents == "project-documents"


def test_non_member_cannot_upload(override_user_repository, monkeypatch) -> None:
    setup_project(override_user_repository)
    monkeypatch.setattr(storage, "upload", lambda *args: (_ for _ in ()).throw(AssertionError()))
    response = client.post(
        "/api/v1/projects/project-documents/documents",
        files=[("files", ("proposal.pdf", b"%PDF-1.7 proposal", "application/pdf"))],
        headers={"Authorization": f"Bearer {token('student@sprintsight.edu')}"},
    )
    assert response.status_code == 403


def test_unsupported_extension_is_rejected(override_user_repository, monkeypatch) -> None:
    setup_project(override_user_repository)
    monkeypatch.setattr(storage, "upload", lambda *args: (_ for _ in ()).throw(AssertionError()))
    response = client.post(
        "/api/v1/projects/project-documents/documents",
        files=[("files", ("notes.bin", b"binary blob", "application/octet-stream"))],
        headers={"Authorization": f"Bearer {token('faculty@sprintsight.edu')}"},
    )
    assert response.status_code == 413


def test_text_based_documents_are_accepted(override_user_repository, monkeypatch) -> None:
    setup_project(override_user_repository, ["u-student-1"])
    objects: dict[str, bytes] = {}
    monkeypatch.setattr(storage, "upload", lambda bucket, key, data, mime_type: objects.setdefault(key, data) and key)
    monkeypatch.setattr(storage, "download", lambda bucket, key: objects[key])
    monkeypatch.setattr(storage, "delete", lambda bucket, key: objects.pop(key, None))
    headers = {"Authorization": f"Bearer {token('student@sprintsight.edu')}"}
    files = [
        ("files", ("brief.md", b"# Project brief\n\nAn example.", "text/markdown")),
        ("files", ("notes.txt", b"Plain text notes.", "text/plain")),
    ]

    upload = client.post("/api/v1/projects/project-documents/documents", files=files, headers=headers)
    assert upload.status_code == 201
    records = upload.json()["documents"]
    assert {record["filename"] for record in records} == {"brief.md", "notes.txt"}
    mime_types = {record["filename"]: record["mime_type"] for record in records}
    assert mime_types["brief.md"] == "text/markdown"
    assert mime_types["notes.txt"] == "text/plain"