from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_admin_assigns_instructor_and_instructor_creates_student_and_project() -> None:
    admin_headers = headers(token("admin@sprintsight.edu"))
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS480", "name": "Capstone", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers)
    assert course.status_code == 201
    course_id = course.json()["id"]
    assert course.json()["created_by"] == "u-faculty-1"

    student = client.post(
        f"/api/v1/courses/{course_id}/students",
        json={"email": "course.student@sprintsight.edu", "full_name": "Course Student", "password": "temporary123"},
        headers=instructor_headers,
    )
    assert student.status_code == 201
    student_id = student.json()["id"]

    project = client.post(
        f"/api/v1/courses/{course_id}/projects",
        json={"project_name": "SprintSight", "description": "Capstone team", "member_ids": [student_id]},
        headers=instructor_headers,
    )
    assert project.status_code == 201
    assert project.json()["members"][0]["id"] == student_id


def test_unassigned_instructor_cannot_create_course_student() -> None:
    admin_headers = headers(token("admin@sprintsight.edu"))
    course_response = client.post("/api/v1/courses", json={"code": "CS490", "name": "Other Course", "section": "001", "year": 2026, "term": "Fall"}, headers=admin_headers)
    assert course_response.status_code == 403

    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS490", "name": "Other Course", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    response = client.post(
        f"/api/v1/courses/{course['id']}/students",
        json={"email": "blocked@sprintsight.edu", "full_name": "Blocked", "password": "temporary123"},
        headers=instructor_headers,
    )
    assert response.status_code == 201


def test_admin_cannot_view_or_manage_projects() -> None:
    admin_headers = headers(token("admin@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS491", "name": "Admin Boundary", "section": "001", "year": 2026, "term": "Fall"}, headers=headers(token("faculty@sprintsight.edu"))).json()
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    assigned = client.post(f"/api/v1/courses/{course['id']}/instructors/u-faculty-1", headers=admin_headers)
    assert assigned.status_code == 200
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json={"project_name": "Instructor Project"},
        headers=instructor_headers,
    ).json()

    assert client.get(f"/api/v1/courses/{course['id']}/projects", headers=admin_headers).status_code == 403
    assert client.get(f"/api/v1/projects/{project['id']}", headers=admin_headers).status_code == 403
    assert client.post(f"/api/v1/projects/{project['id']}/members/u-student-1", headers=admin_headers).status_code == 403


def test_same_course_code_supports_multiple_offerings() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    first = client.post("/api/v1/courses", json={"code": "CS480", "name": "Capstone", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers)
    second = client.post("/api/v1/courses", json={"code": "CS480", "name": "Capstone", "section": "002", "year": 2026, "term": "Fall"}, headers=instructor_headers)
    duplicate = client.post("/api/v1/courses", json={"code": "CS480", "name": "Capstone", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert duplicate.status_code == 409


def test_instructor_can_create_student_without_course_id() -> None:
    response = client.post(
        "/api/v1/students",
        json={"email": "no.course@sprintsight.edu", "full_name": "No Course Student", "password": "temporary123"},
        headers=headers(token("faculty@sprintsight.edu")),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert response.json()["must_change_password"] is True


def test_admin_cannot_use_instructor_student_creation_endpoint() -> None:
    response = client.post(
        "/api/v1/students",
        json={"email": "admin.created@sprintsight.edu", "full_name": "Admin Created", "password": "temporary123"},
        headers=headers(token("admin@sprintsight.edu")),
    )
    assert response.status_code == 403