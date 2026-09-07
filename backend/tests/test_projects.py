from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def project_payload(project_name: str, team_name: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_name": project_name,
        "team_name": team_name,
        "jira_email": "jira.owner@university.edu",
        "jira_domain": "team.atlassian.net",
        "jira_project_key": "JIRA",
        "jira_api_token": "project-jira-token",
    }
    payload.update(extra)
    return payload


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
        json=project_payload("SprintSight", "SprintSight Team", description="Capstone team", member_ids=[student_id]),
        headers=instructor_headers,
    )
    assert project.status_code == 201
    assert project.json()["members"][0]["id"] == student_id


def test_unassigned_instructor_cannot_create_course_student() -> None:
    admin_headers = headers(token("admin@sprintsight.edu"))
    course_response = client.post("/api/v1/courses", json={"code": "CS490", "name": "Other Course", "section": "001", "year": 2026, "term": "Fall"}, headers=admin_headers)
    assert course_response.status_code == 201

    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = course_response.json()
    response = client.post(
        f"/api/v1/courses/{course['id']}/students",
        json={"email": "blocked@sprintsight.edu", "full_name": "Blocked", "password": "temporary123"},
        headers=instructor_headers,
    )
    assert response.status_code == 403


def test_admin_cannot_view_or_manage_projects() -> None:
    admin_headers = headers(token("admin@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS491", "name": "Admin Boundary", "section": "001", "year": 2026, "term": "Fall"}, headers=headers(token("faculty@sprintsight.edu"))).json()
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    assigned = client.post(f"/api/v1/courses/{course['id']}/instructors/u-faculty-1", headers=admin_headers)
    assert assigned.status_code == 200
    project = client.post(
        f"/api/v1/courses/{course['id']}/projects",
        json=project_payload("Instructor Project", "Instructor Team"),
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
        "/api/v1/users",
        json={"email": "no.course@sprintsight.edu", "full_name": "No Course Student", "password": "temporary123"},
        headers=headers(token("faculty@sprintsight.edu")),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert response.json()["must_change_password"] is True


def test_instructor_can_view_all_students_and_section_roster() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS492", "name": "Roster", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    student = client.post(
        f"/api/v1/courses/{course['id']}/students",
        json={"email": "roster.student@sprintsight.edu", "full_name": "Roster Student", "password": "temporary123"},
        headers=instructor_headers,
    ).json()

    all_students = client.get("/api/v1/users", headers=instructor_headers)
    section_students = client.get(f"/api/v1/courses/{course['id']}/students", headers=instructor_headers)
    assert all_students.status_code == 200
    assert any(user["id"] == student["id"] for user in all_students.json())
    assert [user["id"] for user in section_students.json()] == [student["id"]]


def test_student_cannot_enroll_in_two_sections_of_same_course_code() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    first = client.post("/api/v1/courses", json={"code": "CS493", "name": "Enrollment", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    second = client.post("/api/v1/courses", json={"code": "CS493", "name": "Enrollment", "section": "002", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    student = client.post("/api/v1/users", json={"email": "one.section@sprintsight.edu", "full_name": "One Section", "password": "temporary123"}, headers=instructor_headers).json()
    assert client.post(f"/api/v1/courses/{first['id']}/students/{student['id']}", headers=instructor_headers).status_code == 200
    assert client.post(f"/api/v1/courses/{second['id']}/students/{student['id']}", headers=instructor_headers).status_code == 409


def test_unenrolled_student_cannot_join_project() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS494", "name": "Project Enrollment", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    student = client.post("/api/v1/users", json={"email": "not.enrolled@sprintsight.edu", "full_name": "Not Enrolled", "password": "temporary123"}, headers=instructor_headers).json()
    project = client.post(f"/api/v1/courses/{course['id']}/projects", json=project_payload("Needs Enrollment", "Enrollment Team"), headers=instructor_headers).json()
    response = client.post(f"/api/v1/projects/{project['id']}/members/{student['id']}", headers=instructor_headers)
    assert response.status_code == 409


def test_instructor_can_unenroll_student() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    course = client.post("/api/v1/courses", json={"code": "CS495", "name": "Unenrollment", "section": "001", "year": 2026, "term": "Fall"}, headers=instructor_headers).json()
    student = client.post("/api/v1/users", json={"email": "unenroll@sprintsight.edu", "full_name": "Unenroll Me", "password": "temporary123"}, headers=instructor_headers).json()
    assert client.post(f"/api/v1/courses/{course['id']}/students/{student['id']}", headers=instructor_headers).status_code == 200
    assert client.delete(f"/api/v1/courses/{course['id']}/students/{student['id']}", headers=instructor_headers).status_code == 204
    assert client.get(f"/api/v1/courses/{course['id']}/students", headers=instructor_headers).json() == []


def test_admin_can_create_managed_student() -> None:
    response = client.post(
        "/api/v1/users",
        json={"email": "admin.created@sprintsight.edu", "full_name": "Admin Created", "password": "temporary123"},
        headers=headers(token("admin@sprintsight.edu")),
    )
    assert response.status_code == 201
    assert response.json()["role"] == "student"


def test_team_name_is_unique_within_course_but_reusable_across_courses() -> None:
    instructor_headers = headers(token("faculty@sprintsight.edu"))
    first_course = client.post(
        "/api/v1/courses",
        json={"code": "CS496", "name": "Teams One", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    ).json()
    second_course = client.post(
        "/api/v1/courses",
        json={"code": "CS497", "name": "Teams Two", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    ).json()

    first_project = client.post(
        f"/api/v1/courses/{first_course['id']}/projects",
        json=project_payload("First Project", "Team Alpha"),
        headers=instructor_headers,
    )
    duplicate_project = client.post(
        f"/api/v1/courses/{first_course['id']}/projects",
        json=project_payload("Duplicate Project", " team alpha "),
        headers=instructor_headers,
    )
    other_course_project = client.post(
        f"/api/v1/courses/{second_course['id']}/projects",
        json=project_payload("Other Project", "Team Alpha"),
        headers=instructor_headers,
    )

    assert first_project.status_code == 201
    assert duplicate_project.status_code == 409
    assert other_course_project.status_code == 201