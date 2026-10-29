import json

import httpx
from fastapi.testclient import TestClient

from app.core.storage import storage
from app.main import app

client = TestClient(app)


def login(email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_jira_raw_sync_stores_complete_response(monkeypatch) -> None:
    token = login("faculty@sprintsight.edu")
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA480", "name": "Jira Test", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    project_response = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Jira Project",
            "team_name": "Jira Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "JIRA",
            "jira_api_token": "project-jira-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    raw_bytes = b'{"issues":[{"key":"JIRA-1","fields":{"summary":"Raw issue"}}],"total":1}'
    uploaded = {}

    captured_client = {}

    original_init = httpx.Client.__init__

    def fake_init(self, *args, **kwargs):
        captured_client["auth"] = kwargs.get("auth")
        captured_client["base_url"] = kwargs.get("base_url")
        original_init(self, *args, **kwargs)

    original_post = httpx.Client.post

    def fake_post(self, url, **kwargs):
        if url != "/rest/api/3/search/jql":
            return original_post(self, url, **kwargs)
        assert captured_client["auth"] == ("jira.owner@university.edu", "project-jira-token")
        assert captured_client["base_url"] == "https://team.atlassian.net"
        assert kwargs["json"]["jql"] == 'project = "JIRA" AND cf[10020] = "Sprint 1" ORDER BY updated DESC'
        assert kwargs["json"]["fields"] == ["*all"]
        return httpx.Response(200, content=raw_bytes, request=httpx.Request("POST", url))

    def fake_upload(bucket, key, data, mime_type):
        uploaded.update(bucket=bucket, key=key, data=data, mime_type=mime_type)
        return key

    monkeypatch.setattr(httpx.Client, "__init__", fake_init)
    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(storage, "upload", fake_upload)
    response = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-1", "jira_project_key": "JIRA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["issue_count"] == 1
    document = json.loads(uploaded["data"])
    assert document["issues"][0]["key"] == "JIRA-1"
    assert uploaded["mime_type"] == "application/json"
    assert uploaded["key"].startswith(f"raw/jira/{course['id']}/{project['id']}/sprint-1/")


def test_jira_raw_sync_uses_stored_project_key_when_omitted(monkeypatch) -> None:
    token = login("faculty@sprintsight.edu")
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA481", "name": "Jira Stored Key", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Stored Key Project",
            "team_name": "Stored Key Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "STORED",
            "jira_api_token": "project-jira-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    original_post = httpx.Client.post

    def fake_post(self, url, **kwargs):
        if url != "/rest/api/3/search/jql":
            return original_post(self, url, **kwargs)
        assert kwargs["json"]["jql"] == 'project = "STORED" AND cf[10020] = "Sprint 1" ORDER BY updated DESC'
        return httpx.Response(
            200,
            content=b'{"issues":[],"total":0}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(storage, "upload", lambda *args, **kwargs: "raw/jira/key.json")
    response = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["jira_project_key"] == "STORED"


def test_jira_raw_sync_filters_by_requested_sprint(monkeypatch) -> None:
    token = login("faculty@sprintsight.edu")
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA482", "name": "Jira Sprint Filter", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Sprint Filter Project",
            "team_name": "Sprint Filter Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "JIRA",
            "jira_api_token": "project-jira-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    original_post = httpx.Client.post

    def fake_post(self, url, **kwargs):
        if url != "/rest/api/3/search/jql":
            return original_post(self, url, **kwargs)
        assert kwargs["json"]["jql"] == 'project = "JIRA" AND cf[10020] = "Sprint 1" ORDER BY updated DESC'
        return httpx.Response(
            200,
            content=b'{"issues":[],"total":0}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr(storage, "upload", lambda *args, **kwargs: "raw/jira/key.json")
    response = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "Sprint 1", "jira_project_key": "JIRA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["issue_count"] == 0


def test_jira_raw_sync_requires_project_credentials() -> None:
    token = login("faculty@sprintsight.edu")
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA482", "name": "Jira Missing Creds", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "No Creds Project",
            "team_name": "No Creds Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "JIRA",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    response = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-1", "jira_project_key": "JIRA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503


def test_jira_raw_sync_rejects_unassigned_instructor() -> None:
    token = login("faculty@sprintsight.edu")
    response = client.post(
        "/api/v1/jira-ingestion/raw/missing-project",
        json={"sprint_id": "sprint-1", "jira_project_key": "JIRA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Bulk reprocess endpoint tests
# ---------------------------------------------------------------------------


def test_reprocess_all_jira_runs_happy_path(monkeypatch) -> None:
    """Reprocess all runs for a project - happy path."""
    token = login("faculty@sprintsight.edu")
    headers = {"Authorization": f"Bearer {token}"}

    course = client.post(
        "/api/v1/courses",
        json={"code": "REPRO1", "name": "Reprocess Test", "section": "001", "year": 2026, "term": "Fall"},
        headers=headers,
    ).json()

    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Reprocess Project",
            "team_name": "Reprocess Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "REPRO1",
            "jira_api_token": "project-jira-token",
        },
        headers=headers,
    ).json()

    raw_store = {}

    def fake_upload(bucket, key, data, mime_type):
        raw_store[key] = data
        return key

    def fake_download(bucket, key):
        return raw_store[key]

    monkeypatch.setattr(storage, "upload", fake_upload)
    monkeypatch.setattr(storage, "download", fake_download)

    original_post = httpx.Client.post

    def fake_post(self, url, **kwargs):
        if url != "/rest/api/3/search/jql":
            return original_post(self, url, **kwargs)
        return httpx.Response(
            200,
            content=b'{"issues":[{"key":"REPRO-1","fields":{"summary":"Test","customfield_10009":5,"assignee":{"id":"u-student-a","displayName":"Student A","emailAddress":"student.a@sprintsight.edu"}}}],"total":1}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    run1 = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-1", "jira_project_key": "REPRO1"},
        headers=headers,
    ).json()

    run2 = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-2", "jira_project_key": "REPRO1"},
        headers=headers,
    ).json()

    response = client.post(
        f"/api/v1/jira-ingestion/runs/{project['id']}/reprocess-all",
        headers=headers,
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2
    assert all(r["status"] == "processed" for r in results)
    assert {r["run_id"] for r in results} == {run1["run_id"], run2["run_id"]}


def test_reprocess_all_jira_runs_empty(monkeypatch) -> None:
    """Reprocess all runs for a project with no runs - returns empty list."""
    token = login("faculty@sprintsight.edu")

    course = client.post(
        "/api/v1/courses",
        json={"code": "REPRO2", "name": "Empty Project", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Empty Project",
            "team_name": "Empty Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "REPRO2",
            "jira_api_token": "project-jira-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    response = client.post(
        f"/api/v1/jira-ingestion/runs/{project['id']}/reprocess-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_reprocess_all_jira_runs_failed_run(monkeypatch) -> None:
    """Reprocess where one run has bad raw data - returns failed status."""
    token = login("faculty@sprintsight.edu")

    course = client.post(
        "/api/v1/courses",
        json={"code": "REPRO3", "name": "Bad Data Project", "section": "001", "year": 2026, "term": "Fall"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Bad Data Project",
            "team_name": "Bad Data Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "REPRO3",
            "jira_api_token": "project-jira-token",
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    raw_store = {}

    def fake_upload(bucket, key, data, mime_type):
        raw_store[key] = data
        return key

    def fake_download(bucket, key):
        return raw_store[key]

    monkeypatch.setattr(storage, "upload", fake_upload)
    monkeypatch.setattr(storage, "download", fake_download)

    original_post = httpx.Client.post

    def fake_post(self, url, **kwargs):
        if url != "/rest/api/3/search/jql":
            return original_post(self, url, **kwargs)
        return httpx.Response(
            200,
            content=b'{"issues":[{"key":"REPRO-1","fields":{"summary":"Test","customfield_10009":5,"assignee":{"id":"u-student-a","displayName":"Student A","emailAddress":"student.a@sprintsight.edu"}}}],"total":1}',
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    run1 = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-1", "jira_project_key": "REPRO3"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    run2 = client.post(
        f"/api/v1/jira-ingestion/raw/{project['id']}",
        json={"sprint_id": "sprint-2", "jira_project_key": "REPRO3"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()

    raw_store[run2["raw_object_key"]] = b"{invalid json}"

    response = client.post(
        f"/api/v1/jira-ingestion/runs/{project['id']}/reprocess-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 2

    processed = [r for r in results if r["status"] == "processed"]
    failed = [r for r in results if r["status"] == "failed"]

    assert len(processed) == 1
    assert processed[0]["run_id"] == run1["run_id"]

    assert len(failed) == 1
    assert failed[0]["run_id"] == run2["run_id"]
    assert failed[0]["error"] is not None


def test_reprocess_all_jira_runs_403_non_faculty() -> None:
    """Non-faculty user cannot trigger reprocess."""
    token = login("faculty@sprintsight.edu")
    headers = {"Authorization": f"Bearer {token}"}

    course = client.post(
        "/api/v1/courses",
        json={"code": "REPRO4", "name": "Auth Project", "section": "001", "year": 2026, "term": "Fall"},
        headers=headers,
    ).json()

    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Auth Project",
            "team_name": "Auth Team",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "REPRO4",
            "jira_api_token": "project-jira-token",
        },
        headers=headers,
    ).json()

    student_token = login("student@sprintsight.edu")
    student_headers = {"Authorization": f"Bearer {student_token}"}

    response = client.post(
        f"/api/v1/jira-ingestion/runs/{project['id']}/reprocess-all",
        headers=student_headers,
    )
    assert response.status_code == 403