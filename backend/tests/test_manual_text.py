from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def create_project() -> tuple[str, str, dict[str, str]]:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post(
        "/api/v1/courses",
        json={"code": "CS480", "name": "Capstone", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    )
    assert course.status_code == 201
    course_id = course.json()["id"]
    project = client.post(
        f"/api/v1/courses/{course_id}/projects",
        json={
            "project_name": "SprintSight",
            "team_name": "Team One",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "JIRA",
            "jira_api_token": "project-jira-token",
        },
        headers=instructor_headers,
    )
    assert project.status_code == 201
    return course_id, project.json()["id"], instructor_headers


def test_assigned_instructor_can_post_and_get_manual_text() -> None:
    course_id, project_id, instructor_headers = create_project()
    payload = {
        "course_id": course_id,
        "project_id": project_id,
        "sprint_id": "sprint-1",
        "expectations_text": "Focus on clear ownership and meaningful review feedback.",
    }

    saved = client.post("/api/v1/manual-text", json=payload, headers=instructor_headers)
    retrieved = client.get(
        "/api/v1/manual-text",
        params={"course_id": course_id, "project_id": project_id, "sprint_id": "sprint-1"},
        headers=instructor_headers,
    )

    assert saved.status_code == 200
    assert saved.json() == {"status": "saved"}
    assert retrieved.status_code == 200
    assert retrieved.json() == {"expectations_text": payload["expectations_text"]}


def test_manual_text_is_replaced_per_sprint() -> None:
    course_id, project_id, instructor_headers = create_project()
    base = {"course_id": course_id, "project_id": project_id, "sprint_id": "sprint-1"}

    first = {**base, "expectations_text": "First guidance text is long enough."}
    second = {**base, "expectations_text": "Replacement guidance text is long enough."}
    other_sprint = {**base, "sprint_id": "sprint-2", "expectations_text": "Different sprint guidance text."}

    assert client.post("/api/v1/manual-text", json=first, headers=instructor_headers).status_code == 200
    assert client.post("/api/v1/manual-text", json=second, headers=instructor_headers).status_code == 200
    assert client.post("/api/v1/manual-text", json=other_sprint, headers=instructor_headers).status_code == 200

    first_result = client.get("/api/v1/manual-text", params=base, headers=instructor_headers)
    second_result = client.get("/api/v1/manual-text", params=other_sprint, headers=instructor_headers)
    assert first_result.json() == {"expectations_text": second["expectations_text"]}
    assert second_result.json() == {"expectations_text": other_sprint["expectations_text"]}


def test_empty_retrieval_returns_null() -> None:
    course_id, project_id, instructor_headers = create_project()
    response = client.get(
        "/api/v1/manual-text",
        params={"course_id": course_id, "project_id": project_id, "sprint_id": "not-written"},
        headers=instructor_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"expectations_text": None}


def test_manual_text_is_instructor_only() -> None:
    course_id, project_id, instructor_headers = create_project()
    payload = {
        "course_id": course_id,
        "project_id": project_id,
        "sprint_id": "sprint-1",
        "expectations_text": "Instructor-only guidance text is long enough.",
    }

    assert client.post("/api/v1/manual-text", json=payload, headers=headers(token("student@sprintsight.edu"))).status_code == 403
    assert client.get(
        "/api/v1/manual-text",
        params=payload,
        headers=headers(token("admin@sprintsight.edu")),
    ).status_code == 403
    assert client.post("/api/v1/manual-text", json=payload, headers=instructor_headers).status_code == 200