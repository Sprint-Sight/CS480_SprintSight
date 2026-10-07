import json

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SECRET_TOKEN = "jira-secret-token-do-not-echo"


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_project_stores_jira_token_encrypted_and_omits_it_from_responses() -> None:
    instructor = headers(token("faculty@sprintsight.edu"))
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA1", "name": "Jira Creds", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor,
    ).json()
    created = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Cred Project",
            "team_name": "Cred Team",
            "github_repo_url": "https://github.com/org/repo",
            "jira_email": "instructor@university.edu",
            "jira_domain": "https://team.atlassian.net",
            "jira_project_key": "TEAM",
            "jira_api_token": SECRET_TOKEN,
        },
        headers=instructor,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    serialized = json.dumps(body)
    assert SECRET_TOKEN not in serialized
    assert "jira_api_token" not in body
    assert "jira_api_token_encrypted" not in body
    assert body["jira_email"] == "instructor@university.edu"
    assert body["jira_domain"] == "team.atlassian.net"
    assert body["jira_project_key"] == "TEAM"
    assert body["jira_token_configured"] is True

    fetched = client.get(f"/api/v1/projects/{body['id']}", headers=instructor)
    assert fetched.status_code == 200
    assert SECRET_TOKEN not in json.dumps(fetched.json())
    assert fetched.json()["jira_token_configured"] is True


def test_patch_without_token_keeps_configured_flag_and_empty_token_clears_it() -> None:
    instructor = headers(token("faculty@sprintsight.edu"))
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA2", "name": "Jira Patch", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor,
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Patch Project",
            "team_name": "Patch Team",
            "jira_email": "instructor@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "TEAM",
            "jira_api_token": SECRET_TOKEN,
        },
        headers=instructor,
    ).json()

    renamed = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"project_name": "Renamed Project"},
        headers=instructor,
    )
    assert renamed.status_code == 200
    assert renamed.json()["jira_token_configured"] is True
    assert SECRET_TOKEN not in json.dumps(renamed.json())

    cleared = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"jira_api_token": ""},
        headers=instructor,
    )
    assert cleared.status_code == 200
    assert cleared.json()["jira_token_configured"] is False


def test_patch_replaces_token_only_after_jira_validation(monkeypatch) -> None:
    captured_requests: list[httpx.Request] = []
    replacement = "replacement-jira-token-do-not-echo"
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"account_id": "123"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.jiraService.service.httpx.Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    instructor = headers(token("faculty@sprintsight.edu"))
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA3", "name": "Jira Validation", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor,
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Validation Project",
            "team_name": "Validation Team",
            "jira_email": "instructor@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "TEAM",
            "jira_api_token": SECRET_TOKEN,
        },
        headers=instructor,
    ).json()

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"jira_api_token": replacement},
        headers=instructor,
    )

    assert updated.status_code == 200, updated.text
    assert len(captured_requests) == 1
    assert captured_requests[0].url == "https://team.atlassian.net/rest/api/3/search/jql"
    assert captured_requests[0].headers["Authorization"].startswith("Basic ")
    assert replacement not in json.dumps(updated.json())
    assert SECRET_TOKEN not in json.dumps(updated.json())


def test_patch_rejects_invalid_token_without_overwriting_existing_token(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errorMessages": ["Invalid token"]})

    original_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.jiraService.service.httpx.Client",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    instructor = headers(token("faculty@sprintsight.edu"))
    course = client.post(
        "/api/v1/courses",
        json={"code": "JIRA4", "name": "Jira Rejection", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor,
    ).json()
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={
            "project_name": "Rejection Project",
            "team_name": "Rejection Team",
            "jira_email": "instructor@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "TEAM",
            "jira_api_token": SECRET_TOKEN,
        },
        headers=instructor,
    ).json()

    rejected = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"jira_api_token": "invalid-token"},
        headers=instructor,
    )

    assert rejected.status_code == 400
    assert rejected.json()["error"]["message"] == "Jira rejected the credentials or project access."
    assert "invalid-token" not in json.dumps(rejected.json())

    fetched = client.get(f"/api/v1/projects/{project['id']}", headers=instructor)
    assert fetched.status_code == 200
    assert fetched.json()["jira_token_configured"] is True
