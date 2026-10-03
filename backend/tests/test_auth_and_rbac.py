from fastapi.testclient import TestClient

from app.main import app
from app.repositories.in_memory import assessment_repo
from app.schemas.assessment import AssessmentReport, StudentScore, TeamScore
from datetime import datetime, timezone
from app.dependencies.auth import get_assessment_repository


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

    instructor_response = client.get("/api/v1/users", headers=instructor_headers)
    admin_response = client.get("/api/v1/users", headers=admin_headers)

    assert instructor_response.status_code == 200
    assert admin_response.status_code == 200


def test_student_forbidden_on_faculty_route() -> None:
    token = login("student@sprintsight.edu", "password123")
    response = client.post(
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


def test_student_can_view_own_courses_projects_and_reports() -> None:
    instructor_headers = {"Authorization": f"Bearer {login('faculty@sprintsight.edu', 'password123')}"}
    course = client.post(
        "/api/v1/courses",
        json={"code": "CS499", "name": "Student Flow", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    student = client.post(
        f"/api/v1/courses/{course_id}/students",
        json={"email": "student.flow@sprintsight.edu", "full_name": "Student Flow User", "password": "temporary123"},
        headers=instructor_headers,
    )
    assert student.status_code == 201
    student_id = student.json()["id"]
    student_headers = {"Authorization": f"Bearer {login('student.flow@sprintsight.edu', 'temporary123')}"}

    project = client.post(
        f"/api/v1/courses/{course_id}/projects",
        json={
            "project_name": "Student Dashboard Team",
            "team_name": "Alpha Team",
            "description": "Student route validation",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "CS203",
            "jira_api_token": "project-jira-token",
            "member_ids": [student_id],
        },
        headers=instructor_headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    empty_sprints_response = client.get(f"/api/v1/students/projects/{project_id}/sprints", headers=student_headers)
    assert empty_sprints_response.status_code == 200
    assert empty_sprints_response.json() == []

    empty_reports_response = client.get(f"/api/v1/students/projects/{project_id}/reports", headers=student_headers)
    assert empty_reports_response.status_code == 200
    assert empty_reports_response.json() == []

    report = AssessmentReport(
        report_id="rpt-student-flow",
        model_name="mock-rubric-v1",
        mode="mock",
        course_id=course_id,
        project_id=project_id,
        sprint_id="sprint-1",
        generated_at=datetime.now(timezone.utc),
        rubric_weights={"delivery": 0.35, "collaboration": 0.30, "quality": 0.20, "documentation": 0.15},
        team_score=TeamScore(score=85.0, rationale="Good sprint delivery."),
        individual_scores=[StudentScore(student_id=student_id, score=85.0, rationale="Strong contribution.")],
        recommendations=["Keep improving documentation."],
        rubric_scores={},
        strengths=["Delivery"],
        weaknesses=["Documentation"],
    )
    
    app.dependency_overrides[get_assessment_repository]().save_report(report)
    assessment_repo.save_report(report)

    courses_response = client.get("/api/v1/students/courses", headers=student_headers)
    assert courses_response.status_code == 200
    assert any(course_item["id"] == course_id for course_item in courses_response.json())

    projects_response = client.get("/api/v1/students/projects", headers=student_headers)
    assert projects_response.status_code == 200
    assert any(project_item["id"] == project_id for project_item in projects_response.json())

    project_detail_response = client.get(f"/api/v1/students/projects/{project_id}", headers=student_headers)
    assert project_detail_response.status_code == 200
    assert project_detail_response.json()["id"] == project_id

    sprints_response = client.get(f"/api/v1/students/projects/{project_id}/sprints", headers=student_headers)
    assert sprints_response.status_code == 200
    assert "sprint-1" in sprints_response.json()

    reports_response = client.get(f"/api/v1/students/projects/{project_id}/reports", headers=student_headers)
    assert reports_response.status_code == 200
    assert any(item["report_id"] == "rpt-student-flow" for item in reports_response.json())


def test_student_reports_and_sprints_when_list_project_reports_returns_none() -> None:
    instructor_headers = {"Authorization": f"Bearer {login('faculty@sprintsight.edu', 'password123')}"}
    course = client.post(
        "/api/v1/courses",
        json={"code": "CS498", "name": "Empty Reports", "section": "001", "year": 2026, "term": "Fall"},
        headers=instructor_headers,
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    student = client.post(
        f"/api/v1/courses/{course_id}/students",
        json={"email": "student.empty-reports@sprintsight.edu", "full_name": "Empty Reports User", "password": "temporary123"},
        headers=instructor_headers,
    )
    assert student.status_code == 201
    student_id = student.json()["id"]
    student_headers = {"Authorization": f"Bearer {login('student.empty-reports@sprintsight.edu', 'temporary123')}"}

    project = client.post(
        f"/api/v1/courses/{course_id}/projects",
        json={
            "project_name": "Empty Reports Team",
            "team_name": "Beta Team",
            "description": "None reports regression",
            "jira_email": "jira.owner@university.edu",
            "jira_domain": "team.atlassian.net",
            "jira_project_key": "CS204",
            "jira_api_token": "project-jira-token",
            "member_ids": [student_id],
        },
        headers=instructor_headers,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    class NoneReportsRepo:
        def list_project_reports(self, course_id: str, project_id: str):
            return None

    app.dependency_overrides[get_assessment_repository] = lambda: NoneReportsRepo()

    sprints_response = client.get(f"/api/v1/students/projects/{project_id}/sprints", headers=student_headers)
    assert sprints_response.status_code == 200
    assert sprints_response.json() == []

    reports_response = client.get(f"/api/v1/students/projects/{project_id}/reports", headers=student_headers)
    assert reports_response.status_code == 200
    assert reports_response.json() == []
