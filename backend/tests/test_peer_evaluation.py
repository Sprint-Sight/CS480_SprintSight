"""Tests for the peer evaluation feature.

Covers:
- Instructor configuring the evaluation window (open/close + expiry)
- Students submitting 1-5 ratings with remarks for group members
- Students only seeing their own evaluations (not others')
- Instructors seeing all evaluations for a project/course
- Evaluation window enforcement (closed/expired blocks submissions)
- Students updating their own evaluations (PATCH)
- Students/instructors deleting evaluations (DELETE)
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.dependencies.auth import (
    get_assessment_repository,
    get_peer_evaluation_repository,
    get_project_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.in_memory import (
    InMemoryAssessmentRepository,
    InMemoryPeerEvaluationRepository,
    InMemoryProjectRepository,
    InMemoryUserRepository,
)
from app.repositories.interfaces import (
    PeerEvaluationConfigRecord,
    ProjectRecord,
    Role,
    UserRecord,
)

client = TestClient(app)


def _token_for(email: str, password: str = "password123") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _setup_course_with_project():
    """Create a course and project owned by faculty@sprintsight.edu (u-faculty-1)."""
    project_repository = InMemoryProjectRepository()
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-faculty-1",
    )
    # Create two students
    student_a = UserRecord(
        id="u-student-a",
        email="student.a@sprintsight.edu",
        full_name="Student A",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=101,
    )
    student_b = UserRecord(
        id="u-student-b",
        email="student.b@sprintsight.edu",
        full_name="Student B",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=102,
    )
    user_repository = InMemoryUserRepository()
    user_repository.create_user(student_a)
    user_repository.create_user(student_b)

    project = project_repository.create_project(
        ProjectRecord(
            id="proj-peer-1",
            project_name="Peer Project",
            team_name="Peer Team",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        ["u-student-a", "u-student-b"],
    )

    # Enroll students in the course
    project_repository.enroll_student(course.id, "u-student-a")
    project_repository.enroll_student(course.id, "u-student-b")

    return project_repository, course, user_repository, project


def _override_repos(
    project_repository,
    user_repository,
    peer_evaluation_repository,
    assessment_repository=None,
):
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_peer_evaluation_repository] = (
        lambda: peer_evaluation_repository
    )
    if assessment_repository is not None:
        app.dependency_overrides[get_assessment_repository] = (
            lambda: assessment_repository
        )


def _clear_overrides():
    for dep in (
        get_project_repository,
        get_user_repository,
        get_peer_evaluation_repository,
        get_assessment_repository,
    ):
        app.dependency_overrides.pop(dep, None)


# ---------------------------------------------------------------------------
# Instructor: configure evaluation window
# ---------------------------------------------------------------------------


def test_instructor_sets_peer_evaluation_config(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        expires = datetime.now(UTC) + timedelta(days=7)
        response = client.post(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={
                "is_open": True,
                "expires_at": expires.isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["course_id"] == course.id
        assert data["is_open"] is True
        assert data["expires_at"] is not None
    finally:
        _clear_overrides()


def test_instructor_patch_peer_evaluation_config(override_user_repository) -> None:
    """Instructor can update the evaluation window (open/close + expiry) via PATCH."""
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # First open the window
        client.post(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={"is_open": True, "expires_at": None},
            headers=headers,
        )

        # Then update via PATCH: close it and set a new expiry
        new_expiry = datetime.now(UTC) + timedelta(days=14)
        response = client.patch(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={
                "is_open": True,
                "expires_at": new_expiry.isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["course_id"] == course.id
        assert data["is_open"] is True
        assert data["expires_at"] is not None

        # Now close it
        response = client.patch(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={"is_open": False, "expires_at": None},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["is_open"] is False
    finally:
        _clear_overrides()


def test_instructor_gets_peer_evaluation_config(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        # First set config
        client.post(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={"is_open": True, "expires_at": None},
            headers=headers,
        )
        # Then get it
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["course_id"] == course.id
        assert data["is_open"] is True
    finally:
        _clear_overrides()


def test_instructor_403_when_not_assigned_to_course(override_user_repository) -> None:
    """A different instructor cannot configure a course they don't teach."""
    project_repository = InMemoryProjectRepository()
    user_repository = InMemoryUserRepository()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    # Another instructor owns this course
    other_instructor = UserRecord(
        id="u-other-instr",
        email="other.instr@sprintsight.edu",
        full_name="Other Instructor",
        role=Role.INSTRUCTOR,
        hashed_password="x",
    )
    user_repository.create_user(other_instructor)
    course = project_repository.create_course(
        "CS480", "SprintSight", "001", 2026, "Fall", "u-other-instr",
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        # faculty@sprintsight.edu is not assigned
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={"is_open": True, "expires_at": None},
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: submit evaluation
# ---------------------------------------------------------------------------


def test_student_submits_peer_evaluation(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    assessment_repository = InMemoryAssessmentRepository()

    # Open evaluation window
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(
        project_repository, user_repository, peer_eval_repo, assessment_repository
    )

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Great teamwork.",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["rater_id"] == "u-student-a"
        assert data["rated_id"] == "u-student-b"
        assert data["score"] == 4
        assert data["remarks"] == "Great teamwork."
        assert data["project_id"] == "proj-peer-1"
    finally:
        _clear_overrides()


def test_student_cannot_evaluate_self(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-a",  # self
                "score": 5,
            },
            headers=headers,
        )
        assert response.status_code == 400, response.text
    finally:
        _clear_overrides()


def test_student_cannot_evaluate_non_group_member(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    # Add a third student not in the project
    student_c = UserRecord(
        id="u-student-c",
        email="student.c@sprintsight.edu",
        full_name="Student C",
        role=Role.STUDENT,
        hashed_password="x",
        student_number=103,
    )
    user_repository.create_user(student_c)

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-c",  # not in project
                "score": 3,
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


def test_student_cannot_submit_when_window_closed(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    # Config is closed by default (no config saved = not open)

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


def test_student_cannot_submit_when_expired(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # already expired
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
            },
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


def test_resubmission_updates_existing_evaluation(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # First submission
        resp1 = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 3,
                "remarks": "OK work.",
            },
            headers=headers,
        )
        assert resp1.status_code == 201
        eval_id = resp1.json()["evaluation_id"]

        # Re-submission with different score
        resp2 = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 5,
                "remarks": "Improved a lot.",
            },
            headers=headers,
        )
        assert resp2.status_code == 200, resp2.text
        data = resp2.json()
        assert data["evaluation_id"] == eval_id  # same evaluation, updated
        assert data["score"] == 5
        assert data["remarks"] == "Improved a lot."

        # Verify only one evaluation exists for this pair
        my_evals = client.get(
            "/api/v1/peer-evaluation/evaluations/mine",
            headers=headers,
        )
        assert my_evals.status_code == 200
        mine = my_evals.json()
        matching = [e for e in mine if e["rated_id"] == "u-student-b"]
        assert len(matching) == 1
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: patch (update) own evaluation
# ---------------------------------------------------------------------------


def test_student_patches_own_evaluation(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # First submission
        resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 3,
                "remarks": "OK work.",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        eval_id = resp.json()["evaluation_id"]

        # PATCH: update score and remarks
        patch_resp = client.patch(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            json={
                "score": 5,
                "remarks": "Much better now.",
            },
            headers=headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        data = patch_resp.json()
        assert data["evaluation_id"] == eval_id
        assert data["score"] == 5
        assert data["remarks"] == "Much better now."

        # PATCH: update only remarks
        patch_resp2 = client.patch(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            json={
                "remarks": "Final thoughts.",
            },
            headers=headers,
        )
        assert patch_resp2.status_code == 200, patch_resp2.text
        data2 = patch_resp2.json()
        assert data2["score"] == 5  # unchanged
        assert data2["remarks"] == "Final thoughts."
    finally:
        _clear_overrides()


def test_student_cannot_patch_another_students_evaluation(
    override_user_repository,
) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        token_b = _token_for("student.b@sprintsight.edu")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Student A creates an evaluation
        resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Good job.",
            },
            headers=headers_a,
        )
        assert resp.status_code == 201
        eval_id = resp.json()["evaluation_id"]

        # Student B tries to patch Student A's evaluation
        patch_resp = client.patch(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            json={"score": 1},
            headers=headers_b,
        )
        assert patch_resp.status_code == 403, patch_resp.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: delete own evaluation
# ---------------------------------------------------------------------------


def test_student_deletes_own_evaluation(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # Create an evaluation
        resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "To be deleted.",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        eval_id = resp.json()["evaluation_id"]

        # Delete it
        del_resp = client.delete(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            headers=headers,
        )
        assert del_resp.status_code == 204, del_resp.text

        # Verify it's gone from "mine"
        mine = client.get(
            "/api/v1/peer-evaluation/evaluations/mine",
            headers=headers,
        )
        assert mine.status_code == 200
        assert len(mine.json()) == 0
    finally:
        _clear_overrides()


def test_student_cannot_delete_another_students_evaluation(
    override_user_repository,
) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        token_b = _token_for("student.b@sprintsight.edu")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Student A creates an evaluation
        resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Good job.",
            },
            headers=headers_a,
        )
        assert resp.status_code == 201
        eval_id = resp.json()["evaluation_id"]

        # Student B tries to delete Student A's evaluation
        del_resp = client.delete(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            headers=headers_b,
        )
        assert del_resp.status_code == 403, del_resp.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Instructor: delete any evaluation
# ---------------------------------------------------------------------------


def test_instructor_can_delete_any_evaluation(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        token_faculty = _token_for("faculty@sprintsight.edu")
        headers_faculty = {"Authorization": f"Bearer {token_faculty}"}

        # Student A creates an evaluation
        resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Good job.",
            },
            headers=headers_a,
        )
        assert resp.status_code == 201
        eval_id = resp.json()["evaluation_id"]

        # Instructor deletes it
        del_resp = client.delete(
            f"/api/v1/peer-evaluation/evaluations/{eval_id}",
            headers=headers_faculty,
        )
        assert del_resp.status_code == 204, del_resp.text

        # Verify instructor no longer sees it
        proj_evals = client.get(
            "/api/v1/peer-evaluation/projects/proj-peer-1/evaluations",
            headers=headers_faculty,
        )
        assert proj_evals.status_code == 200
        assert len(proj_evals.json()["evaluations"]) == 0
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: view own evaluations
# ---------------------------------------------------------------------------


def test_student_sees_only_own_evaluations(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        token_b = _token_for("student.b@sprintsight.edu")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Student A evaluates Student B
        client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Good job.",
            },
            headers=headers_a,
        )
        # Student B evaluates Student A
        client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-a",
                "score": 5,
                "remarks": "Great partner.",
            },
            headers=headers_b,
        )

        # Student A should only see their own evaluation (of B), not B's evaluation of A
        mine_a = client.get(
            "/api/v1/peer-evaluation/evaluations/mine",
            headers=headers_a,
        )
        assert mine_a.status_code == 200
        evals_a = mine_a.json()
        assert len(evals_a) == 1
        assert evals_a[0]["rater_id"] == "u-student-a"
        assert evals_a[0]["rated_id"] == "u-student-b"

        mine_b = client.get(
            "/api/v1/peer-evaluation/evaluations/mine",
            headers=headers_b,
        )
        assert mine_b.status_code == 200
        evals_b = mine_b.json()
        assert len(evals_b) == 1
        assert evals_b[0]["rater_id"] == "u-student-b"
        assert evals_b[0]["rated_id"] == "u-student-a"
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Instructor: view all evaluations
# ---------------------------------------------------------------------------


def test_instructor_sees_all_project_evaluations(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}
        token_b = _token_for("student.b@sprintsight.edu")
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Both students submit evaluations
        client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Good job.",
            },
            headers=headers_a,
        )
        client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-a",
                "score": 5,
                "remarks": "Great partner.",
            },
            headers=headers_b,
        )

        # Instructor fetches all evaluations for the project
        token_faculty = _token_for("faculty@sprintsight.edu")
        headers_faculty = {"Authorization": f"Bearer {token_faculty}"}
        response = client.get(
            "/api/v1/peer-evaluation/projects/proj-peer-1/evaluations",
            headers=headers_faculty,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["project_id"] == "proj-peer-1"
        assert data["project_name"] == "Peer Project"
        assert data["total_evaluations"] == 2
        assert data["average_score"] == 4.5
        assert len(data["evaluations"]) == 2

        # Verify both raters are visible to instructor
        rater_ids = {e["rater_id"] for e in data["evaluations"]}
        assert rater_ids == {"u-student-a", "u-student-b"}
    finally:
        _clear_overrides()


def test_instructor_sees_all_course_evaluations(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token_a = _token_for("student.a@sprintsight.edu")
        headers_a = {"Authorization": f"Bearer {token_a}"}

        client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
            },
            headers=headers_a,
        )

        token_faculty = _token_for("faculty@sprintsight.edu")
        headers_faculty = {"Authorization": f"Bearer {token_faculty}"}
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/evaluations",
            headers=headers_faculty,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["course_id"] == course.id
        assert data["total_projects"] == 1
        assert data["total_evaluations"] == 1
    finally:
        _clear_overrides()


def test_instructor_403_viewing_other_course_evaluations(override_user_repository) -> None:
    project_repository = InMemoryProjectRepository()
    user_repository = InMemoryUserRepository()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    other_instructor = UserRecord(
        id="u-other-instr-2",
        email="other2.instr@sprintsight.edu",
        full_name="Other Instructor 2",
        role=Role.INSTRUCTOR,
        hashed_password="x",
    )
    user_repository.create_user(other_instructor)
    course = project_repository.create_course(
        "CS499", "Other Course", "A", 2026, "Fall", "u-other-instr-2",
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/evaluations",
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: evaluation status with opens_at (scheduled open/close)
# ---------------------------------------------------------------------------


def test_student_cannot_evaluate_before_opens_at(override_user_repository) -> None:
    """Student cannot submit when opens_at is in the future, even if is_open=True."""
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            opens_at=datetime.now(UTC) + timedelta(days=7),  # opens next week
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # Status should show can_evaluate=False
        status_resp = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/status",
            headers=headers,
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["can_evaluate"] is False
        assert status_data["is_open"] is True
        assert status_data["opens_at"] is not None

        # Submission should be rejected
        submit_resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
            },
            headers=headers,
        )
        assert submit_resp.status_code == 403, submit_resp.text
    finally:
        _clear_overrides()


def test_student_can_evaluate_after_opens_at(override_user_repository) -> None:
    """Student can submit once opens_at has passed."""
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            opens_at=datetime.now(UTC) - timedelta(minutes=5),  # opened 5 min ago
            expires_at=datetime.now(UTC) + timedelta(days=7),
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        # Status should show can_evaluate=True
        status_resp = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/status",
            headers=headers,
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["can_evaluate"] is True
        assert status_data["is_open"] is True

        # Submission should succeed
        submit_resp = client.post(
            "/api/v1/peer-evaluation/evaluations",
            json={
                "project_id": "proj-peer-1",
                "rated_id": "u-student-b",
                "score": 4,
                "remarks": "Great work.",
            },
            headers=headers,
        )
        assert submit_resp.status_code == 201, submit_resp.text
    finally:
        _clear_overrides()


def test_instructor_sets_opens_at_and_expires_at(override_user_repository) -> None:
    """Instructor can set both opens_at and expires_at in one config call."""
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}

        opens = datetime.now(UTC) + timedelta(days=1)
        expires = datetime.now(UTC) + timedelta(days=7)

        response = client.post(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            json={
                "is_open": True,
                "opens_at": opens.isoformat(),
                "expires_at": expires.isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["is_open"] is True
        assert data["opens_at"] is not None
        assert data["expires_at"] is not None

        # GET config should return both dates
        get_resp = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/config",
            headers=headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["opens_at"] is not None
        assert get_data["expires_at"] is not None
    finally:
        _clear_overrides()
    project_repository = InMemoryProjectRepository()
    user_repository = InMemoryUserRepository()
    peer_eval_repo = InMemoryPeerEvaluationRepository()

    other_instructor = UserRecord(
        id="u-other-instr-2",
        email="other2.instr@sprintsight.edu",
        full_name="Other Instructor 2",
        role=Role.INSTRUCTOR,
        hashed_password="x",
    )
    user_repository.create_user(other_instructor)
    course = project_repository.create_course(
        "CS499", "Other Course", "A", 2026, "Fall", "u-other-instr-2",
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/evaluations",
            headers=headers,
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Student: evaluation status
# ---------------------------------------------------------------------------


def test_student_evaluation_status_when_open(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/status",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["can_evaluate"] is True
        assert data["is_open"] is True
    finally:
        _clear_overrides()


def test_student_evaluation_status_when_closed(override_user_repository) -> None:
    project_repository, course, user_repository, project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    # No config = closed

    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/peer-evaluation/courses/{course.id}/status",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["can_evaluate"] is False
        assert data["is_open"] is False
    finally:
        _clear_overrides()


# ---------------------------------------------------------------------------
# Instructor: member received-evaluations + outlier stats
# ---------------------------------------------------------------------------


def _setup_course_with_four_students():
    project_repository, course, user_repository, _project = _setup_course_with_project()
    student_c = UserRecord(
        id="u-student-c",
        email="student.c@sprintsight.edu",
        full_name="Student C",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=103,
    )
    student_d = UserRecord(
        id="u-student-d",
        email="student.d@sprintsight.edu",
        full_name="Student D",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=104,
    )
    student_e = UserRecord(
        id="u-student-e",
        email="student.e@sprintsight.edu",
        full_name="Student E",
        role=Role.STUDENT,
        hashed_password=hash_password("password123"),
        student_number=105,
    )
    user_repository.create_user(student_c)
    user_repository.create_user(student_d)
    user_repository.create_user(student_e)
    project_repository.set_members(
        "proj-peer-1",
        ["u-student-a", "u-student-b", "u-student-c", "u-student-d"],
    )
    project_repository.enroll_student(course.id, "u-student-c")
    project_repository.enroll_student(course.id, "u-student-d")
    project_repository.enroll_student(course.id, "u-student-e")
    return project_repository, course, user_repository


def test_instructor_gets_member_evaluations_with_outlier_stats(
    override_user_repository,
) -> None:
    project_repository, course, user_repository = _setup_course_with_four_students()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    peer_eval_repo.save_config(
        PeerEvaluationConfigRecord(
            course_id=course.id,
            is_open=True,
            expires_at=None,
            updated_by="u-faculty-1",
            updated_at=datetime.now(UTC),
        )
    )
    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        tokens = {
            "a": _token_for("student.a@sprintsight.edu"),
            "b": _token_for("student.b@sprintsight.edu"),
            "c": _token_for("student.c@sprintsight.edu"),
            "d": _token_for("student.d@sprintsight.edu"),
        }

        def submit(rater: str, rated_id: str, score: int, remarks: str) -> None:
            response = client.post(
                "/api/v1/peer-evaluation/evaluations",
                json={
                    "project_id": "proj-peer-1",
                    "rated_id": rated_id,
                    "score": score,
                    "remarks": remarks,
                },
                headers={"Authorization": f"Bearer {tokens[rater]}"},
            )
            assert response.status_code in (200, 201), response.text

        # Totals: A=15, B=12, C=7, D=13. Enrolled E has no evaluations (total 0).
        submit("b", "u-student-a", 5, "Strong contributor")
        submit("c", "u-student-a", 5, "Always delivers")
        submit("d", "u-student-a", 5, "Reliable teammate")
        submit("a", "u-student-b", 4, "Solid work")
        submit("c", "u-student-b", 4, "Consistent")
        submit("d", "u-student-b", 4, "Helpful")
        submit("a", "u-student-c", 1, "Needs to participate more")
        submit("b", "u-student-c", 1, "Rarely available")
        submit("d", "u-student-c", 5, "Helped me on the demo")
        submit("a", "u-student-d", 4, "Good communicator")
        submit("b", "u-student-d", 4, "Met deadlines")
        submit("c", "u-student-d", 5, "Led the sprint")

        token_faculty = _token_for("faculty@sprintsight.edu")
        headers_faculty = {"Authorization": f"Bearer {token_faculty}"}
        response = client.get(
            "/api/v1/peer-evaluation/projects/proj-peer-1/members/u-student-c/evaluations",
            headers=headers_faculty,
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["member_id"] == "u-student-c"
        assert data["member_full_name"] == "Student C"
        assert data["total_score"] == 7
        assert data["evaluation_count"] == 3
        assert data["enrolled_student_count"] == 5
        assert data["students_with_received_evaluations"] == 4
        # Course mean of received totals is 11.75; C=7 and unevaluated E=0 are below it.
        assert data["course_average_total"] == 11.75
        assert data["students_below_course_average"] == 2
        assert data["is_total_outlier"] is True
        assert data["outlier_direction"] == "low"

        remarks = {item["rater_id"]: item["remarks"] for item in data["evaluations"]}
        assert remarks["u-student-a"] == "Needs to participate more"
        assert remarks["u-student-b"] == "Rarely available"
        assert remarks["u-student-d"] == "Helped me on the demo"

        outlier_scores = [
            item["score"] for item in data["evaluations"] if item["is_score_outlier"]
        ]
        assert outlier_scores == [5]
    finally:
        _clear_overrides()


def test_student_cannot_get_member_evaluations(override_user_repository) -> None:
    project_repository, course, user_repository, _project = _setup_course_with_project()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("student.a@sprintsight.edu")
        response = client.get(
            "/api/v1/peer-evaluation/projects/proj-peer-1/members/u-student-b/evaluations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, response.text
    finally:
        _clear_overrides()


def test_member_evaluations_404_when_not_in_project(override_user_repository) -> None:
    project_repository, course, user_repository = _setup_course_with_four_students()
    peer_eval_repo = InMemoryPeerEvaluationRepository()
    _override_repos(project_repository, user_repository, peer_eval_repo)

    try:
        token = _token_for("faculty@sprintsight.edu")
        response = client.get(
            "/api/v1/peer-evaluation/projects/proj-peer-1/members/u-student-e/evaluations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404, response.text
    finally:
        _clear_overrides()

