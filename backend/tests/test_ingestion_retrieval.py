from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.dependencies.auth import get_metrics_repository
from app.main import app
from app.repositories.in_memory import InMemoryMetricsRepository
from app.repositories.interfaces import IngestionMetricBundle, ProjectRecord
from app.schemas.assessment import CommitInfo, FileDiff


client = TestClient(app)


def token() -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "faculty@sprintsight.edu", "password": "password123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_retrieve_stored_commits_and_file_changes(override_user_repository) -> None:
    project_repository = override_user_repository
    project_repository.create_course("CS480", "Capstone", "001", 2026, "Fall", "u-faculty-1")
    project_repository.create_project(
        ProjectRecord(
            id="project-retrieval",
            project_name="Retrieval Project",
            team_name="Retrieval Team",
            description=None,
            course_id="course-retrieval",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="cs-203-project",
            created_by="u-faculty-1",
            created_at=datetime.now(timezone.utc),
        ),
        [],
    )
    project_repository.assign_instructor("course-retrieval", "u-faculty-1")

    metrics_repository = InMemoryMetricsRepository()
    captured_at = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    metrics_repository.save_metrics(
        IngestionMetricBundle(
            course_id="course-retrieval",
            project_id="project-retrieval",
            sprint_id="sprint-1",
            commit_frequency=2.0,
            code_churn=12,
            pr_turnaround_hours=None,
            assigned_story_points=None,
            completion_percent=None,
            commits=[
                CommitInfo(
                    sha="abc123",
                    author="Student One",
                    author_email="student@example.com",
                    message="Add authentication",
                    timestamp=captured_at,
                    lines_added=10,
                    lines_deleted=2,
                    files_changed=[
                        FileDiff(
                            filename="src/auth.py",
                            change_type="modified",
                            lines_added=10,
                            lines_deleted=2,
                        )
                    ],
                )
            ],
            local_repo_path=str(Path("C:/private/repo")),
            head_sha="abc123",
            captured_at=captured_at,
        )
    )
    app.dependency_overrides[get_metrics_repository] = lambda: metrics_repository

    try:
        response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={
                "course_id": "course-retrieval",
                "pagination": True,
                "limit": 10,
                "offset": 0,
            },
            headers={"Authorization": f"Bearer {token()}"},
        )
        complete_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={"course_id": "course-retrieval"},
            headers={"Authorization": f"Bearer {token()}"},
        )
        invalid_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={"course_id": "course-retrieval", "limit": 10},
            headers={"Authorization": f"Bearer {token()}"},
        )
        filtered_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={
                "course_id": "course-retrieval",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
            headers={"Authorization": f"Bearer {token()}"},
        )
        empty_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={
                "course_id": "course-retrieval",
                "pagination": True,
                "limit": 10,
                "offset": 0,
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
            },
            headers={"Authorization": f"Bearer {token()}"},
        )
        incomplete_range_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={"course_id": "course-retrieval", "start_date": "2026-01-01"},
            headers={"Authorization": f"Bearer {token()}"},
        )
        reversed_range_response = client.get(
            "/api/v1/repo-ingestion/runs/project-retrieval/sprint-1",
            params={
                "course_id": "course-retrieval",
                "start_date": "2026-02-01",
                "end_date": "2026-01-31",
            },
            headers={"Authorization": f"Bearer {token()}"},
        )
    finally:
        app.dependency_overrides.pop(get_metrics_repository, None)

    assert response.status_code == 200
    body = response.json()
    assert body["head_sha"] == "abc123"
    assert body["commits"][0]["author_email"] == "student@example.com"
    assert body["commits"][0]["student_id"] is None
    assert body["commits"][0]["files_changed"] == [
        {
            "filename": "src/auth.py",
            "change_type": "modified",
            "lines_added": 10,
            "lines_deleted": 2,
        }
    ]
    assert body["pagination"] == {"limit": 10, "offset": 0, "total": 1, "has_more": False}
    assert "C:/private/repo" not in response.text
    assert complete_response.status_code == 200
    assert len(complete_response.json()["commits"]) == 1
    assert complete_response.json()["pagination"] == {
        "limit": None,
        "offset": None,
        "total": 1,
        "has_more": False,
    }
    assert invalid_response.status_code == 422
    assert filtered_response.status_code == 200
    assert len(filtered_response.json()["commits"]) == 1
    assert empty_response.status_code == 200
    assert empty_response.json()["commits"] == []
    assert empty_response.json()["pagination"]["total"] == 0
    assert incomplete_range_response.status_code == 422
    assert reversed_range_response.status_code == 422
