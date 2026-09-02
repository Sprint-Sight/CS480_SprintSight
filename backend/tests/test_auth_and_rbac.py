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


def test_admin_and_instructor_share_faculty_routes() -> None:
    instructor_headers = {"Authorization": f"Bearer {login('faculty@sprintsight.edu', 'password123')}"}
    admin_headers = {"Authorization": f"Bearer {login('admin@sprintsight.edu', 'password123')}"}

    instructor_response = client.get("/api/v1/students", headers=instructor_headers)
    admin_response = client.get("/api/v1/students", headers=admin_headers)

    assert instructor_response.status_code == 200
    assert admin_response.status_code == 200


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


def test_logout_revokes_instructor_token() -> None:
    token = login("faculty@sprintsight.edu", "password123")

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401


def test_logout_revokes_student_token() -> None:
    token = login("student@sprintsight.edu", "password123")

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401
