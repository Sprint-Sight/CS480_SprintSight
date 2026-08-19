from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def login(email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_success_faculty() -> None:
    token = login("faculty@sprintsight.edu", "password123")
    assert token


def test_student_forbidden_on_faculty_route() -> None:
    token = login("student@sprintsight.edu", "password123")
    response = client.put(
        "/api/v1/manual-text",
        json={
            "course_id": "cs480",
            "project_id": "p1",
            "sprint_id": "s1",
            "expectations_text": "Students should provide detailed test evidence.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
