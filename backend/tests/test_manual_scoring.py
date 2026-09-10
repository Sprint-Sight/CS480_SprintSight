from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.interfaces import ProjectRecord

client = TestClient(app)


def token(email: str, password: str = "password123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(email)}"}


def setup_project(repository) -> None:
    repository.create_project(
        ProjectRecord(
            id="manual-project",
            project_name="Manual Project",
            team_name="Manual Team",
            description=None,
            course_id="manual-course",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        ["u-student-1"],
    )
    repository.assign_instructor("manual-course", "u-faculty-1")


def payload(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "course_id": "manual-course",
        "project_id": "manual-project",
        "sprint_id": "sprint-1",
        "requirements_score": 80,
        "code_quality_score": 90,
        "testing_score": 70,
        "documentation_score": 100,
        "collaboration_score": 60,
    }
    result.update(overrides)
    return result


def test_instructor_can_create_and_update_manual_override(override_user_repository) -> None:
    setup_project(override_user_repository)
    response = client.post(
        "/api/v1/manual-scoring/overrides",
        json=payload(),
        headers=headers("faculty@sprintsight.edu"),
    )
    assert response.status_code == 200
    first = response.json()
    assert UUID(first["override_id"])
    assert first["team_name"] == "Manual Team"
    assert first["total_score"] == 80

    updated = client.post(
        "/api/v1/manual-scoring/overrides",
        json=payload(requirements_score=100, collaboration_score=100),
        headers=headers("faculty@sprintsight.edu"),
    )
    assert updated.status_code == 200
    second = updated.json()
    assert second["override_id"] == first["override_id"]
    assert second["total_score"] == 92


def test_project_member_can_view_manual_override(override_user_repository) -> None:
    setup_project(override_user_repository)
    client.post(
        "/api/v1/manual-scoring/overrides",
        json=payload(),
        headers=headers("faculty@sprintsight.edu"),
    )
    response = client.get(
        "/api/v1/manual-scoring/overrides",
        params={
            "course_id": "manual-course",
            "project_id": "manual-project",
            "sprint_id": "sprint-1",
        },
        headers=headers("student@sprintsight.edu"),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["project_id"] == "manual-project"


def test_mismatched_course_is_rejected(override_user_repository) -> None:
    setup_project(override_user_repository)
    response = client.post(
        "/api/v1/manual-scoring/overrides",
        json=payload(course_id="different-course"),
        headers=headers("faculty@sprintsight.edu"),
    )
    assert response.status_code == 400


def test_scores_must_be_between_zero_and_hundred(override_user_repository) -> None:
    setup_project(override_user_repository)
    response = client.post(
        "/api/v1/manual-scoring/overrides",
        json=payload(testing_score=101),
        headers=headers("faculty@sprintsight.edu"),
    )
    assert response.status_code == 422
