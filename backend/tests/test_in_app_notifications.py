from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.dependencies.auth import get_notification_repository
from app.main import app
from app.repositories.interfaces import NotificationRecord, ProjectRecord

client = TestClient(app)


def _token(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_course_and_project_additions_notify_student(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS480",
        "SprintSight",
        "001",
        2026,
        "Fall",
        "u-faculty-1",
    )
    instructor_headers = {
        "Authorization": f"Bearer {_token('faculty@sprintsight.edu')}",
    }
    student_headers = {
        "Authorization": f"Bearer {_token('student@sprintsight.edu')}",
    }

    enrollment = client.post(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )

    assert enrollment.status_code == 200, enrollment.text
    repository = app.dependency_overrides[get_notification_repository]()
    assert repository.list_notifications("u-student-1")[0].event_type == "course_enrollment"

    project = ProjectRecord(
        id=str(uuid4()),
        project_name="Notification Project",
        team_name="Notification Team",
        description=None,
        course_id=course.id,
        course_code=course.code,
        github_repo_url=None,
        local_repo_path=None,
        created_by="u-faculty-1",
        created_at=datetime.now(timezone.utc),
    )
    override_user_repository.create_project(project, [])
    assigned = client.post(
        f"/api/v1/projects/{project.id}/members/u-student-1",
        headers=instructor_headers,
    )

    assert assigned.status_code == 200, assigned.text
    student_feed = client.get("/api/v1/notifications", headers=student_headers)
    assert student_feed.status_code == 200
    response = student_feed.json()
    assert response["unread_count"] == 2
    assert {item["event_type"] for item in response["notifications"]} == {
        "course_enrollment",
        "project_membership",
    }

    notification_id = response["notifications"][0]["id"]
    marked = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=student_headers,
    )
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None

    instructor_feed = client.get("/api/v1/notifications", headers=instructor_headers)
    assert instructor_feed.json()["notifications"] == []


def test_user_cannot_mark_another_users_notification_read(
    override_user_repository,
) -> None:
    course = override_user_repository.create_course(
        "CS481",
        "Notification Access",
        "001",
        2026,
        "Fall",
        "u-faculty-1",
    )
    override_user_repository.enroll_student(course.id, "u-student-1")
    instructor = client.post(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers={"Authorization": f"Bearer {_token('faculty@sprintsight.edu')}"},
    )
    assert instructor.status_code == 409

    repository = app.dependency_overrides[get_notification_repository]()
    notification_id = str(uuid4())
    repository.create_notification(
        NotificationRecord(
            id=notification_id,
            recipient_id="u-faculty-1",
            event_type="private",
            title="Private",
            message="Not for students",
            created_at=datetime.now(timezone.utc),
        )
    )
    response = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {_token('student@sprintsight.edu')}"},
    )
    assert response.status_code == 404
