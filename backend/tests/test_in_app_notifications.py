from datetime import UTC, datetime, timezone
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


def _project(
    course_id: str,
    name: str = "Removal Project",
    team: str = "Removal Team",
) -> ProjectRecord:
    return ProjectRecord(
        id=str(uuid4()),
        project_name=name,
        team_name=team,
        description=None,
        course_id=course_id,
        course_code="CS480",
        github_repo_url=None,
        local_repo_path=None,
        created_by="u-faculty-1",
        created_at=datetime.now(UTC),
    )


def test_removing_a_student_from_a_course_notifies_them(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS482",
        "Removal Course",
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

    project = _project(course.id)
    override_user_repository.create_project(project, ["u-student-1"])

    removal = client.delete(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )
    assert removal.status_code == 204, removal.text

    response = client.get("/api/v1/notifications", headers=student_headers)
    assert response.status_code == 200
    removals = [
        item
        for item in response.json()["notifications"]
        if item["event_type"] == "course_unenrollment"
    ]
    assert len(removals) == 1
    assert removals[0]["title"] == "Removed from a course"
    assert "CS482" in removals[0]["message"]
    # Unenrolling also dropped them from the project group, so it is named.
    assert "Removal Team" in removals[0]["message"]
    assert not override_user_repository.is_student_enrolled(course.id, "u-student-1")
    assert "u-student-1" not in override_user_repository.list_member_ids(project.id)


def test_removing_a_student_from_a_project_group_notifies_them(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS483",
        "Group Removal",
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

    client.post(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )
    project = _project(course.id, "Group Removal Project", "Alpha Squad")
    override_user_repository.create_project(project, ["u-student-1"])

    removal = client.delete(
        f"/api/v1/projects/{project.id}/members/u-student-1",
        headers=instructor_headers,
    )
    assert removal.status_code == 200, removal.text

    response = client.get("/api/v1/notifications", headers=student_headers)
    removals = [
        item
        for item in response.json()["notifications"]
        if item["event_type"] == "project_unmembership"
    ]
    assert len(removals) == 1
    assert removals[0]["title"] == "Removed from a project"
    assert "Alpha Squad" in removals[0]["message"]
    # The student stays enrolled in the course; only the group membership ended.
    assert override_user_repository.is_student_enrolled(course.id, "u-student-1")
    assert "u-student-1" not in override_user_repository.list_member_ids(project.id)


def test_deleting_a_course_notifies_its_students(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS485",
        "Deleted Course",
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

    client.post(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )
    project = _project(course.id, "Doomed Project", "Doomed Team")
    override_user_repository.create_project(project, ["u-student-1"])

    deletion = client.delete(f"/api/v1/courses/{course.id}", headers=instructor_headers)
    assert deletion.status_code == 200, deletion.text

    response = client.get("/api/v1/notifications", headers=student_headers)
    deletions = [
        item
        for item in response.json()["notifications"]
        if item["event_type"] == "course_deletion"
    ]
    assert len(deletions) == 1
    assert deletions[0]["title"] == "Course deleted"
    assert "CS485" in deletions[0]["message"]
    # The project group went with the course, so it is named.
    assert "Doomed Team" in deletions[0]["message"]
    assert override_user_repository.get_course(course.id) is None


def test_deleting_a_project_group_notifies_its_members(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS486",
        "Project Deletion",
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

    client.post(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )
    project = _project(course.id, "Cancelled Project", "Cancelled Squad")
    override_user_repository.create_project(project, ["u-student-1"])

    deletion = client.delete(f"/api/v1/projects/{project.id}", headers=instructor_headers)
    assert deletion.status_code == 200, deletion.text

    response = client.get("/api/v1/notifications", headers=student_headers)
    deletions = [
        item
        for item in response.json()["notifications"]
        if item["event_type"] == "project_deletion"
    ]
    assert len(deletions) == 1
    assert deletions[0]["title"] == "Project deleted"
    assert "Cancelled Squad" in deletions[0]["message"]
    # The course survives a project deletion, so the student stays enrolled.
    assert override_user_repository.is_student_enrolled(course.id, "u-student-1")
    assert override_user_repository.get_project(project.id) is None


def test_unenrolling_an_unenrolled_student_does_not_notify(override_user_repository) -> None:
    course = override_user_repository.create_course(
        "CS484",
        "No Such Enrollment",
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

    removal = client.delete(
        f"/api/v1/courses/{course.id}/students/u-student-1",
        headers=instructor_headers,
    )
    assert removal.status_code == 404

    response = client.get("/api/v1/notifications", headers=student_headers)
    assert response.json()["notifications"] == []


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
