import json

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
