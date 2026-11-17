"""Commit / Jira attribution must not depend on the order students, teams and syncs are set up."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies.auth import (
    get_git_identity_repository,
    get_jira_ingestion_repository,
    get_metrics_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.in_memory import (
    InMemoryGitIdentityRepository,
    InMemoryJiraIngestionRunRepository,
    InMemoryMetricsRepository,
)
from app.repositories.interfaces import IngestionMetricBundle, ProjectRecord, UserRecord
from app.schemas.assessment import CommitInfo, JiraCleanedSnapshot, JiraTicket
from app.schemas.auth import Role
from app.services.gitlabGithub import service as git_service
from app.services.identityService.service import (
    apply_to_snapshot,
    build_resolver,
    relink_project,
)

client = TestClient(app)
NOW = datetime(2026, 1, 15, 12, tzinfo=UTC)
P = "00000000-0000-4000-8000-0000000000a1"
ADA = "00000000-0000-4000-8000-0000000000b1"
BOB = "00000000-0000-4000-8000-0000000000b2"
T1 = "00000000-0000-4000-8000-0000000000b3"
T2 = "00000000-0000-4000-8000-0000000000b4"
GONE = "00000000-0000-4000-8000-0000000000b5"
LEFT = "00000000-0000-4000-8000-0000000000b6"
OUTSIDER = "00000000-0000-4000-8000-0000000000b7"
ELSE = "00000000-0000-4000-8000-0000000000b8"
ONE = "00000000-0000-4000-8000-0000000000b9"


def _student(user_id: str, email: str, name: str, active: bool = True) -> UserRecord:
    return UserRecord(user_id, email, name, Role.STUDENT, "hash", is_active=active)


def _commit(sha: str, author: str, email: str | None, student_id: str | None = None) -> CommitInfo:
    return CommitInfo(
        sha=sha,
        author=author,
        author_email=email,
        student_id=student_id,
        message="m",
        timestamp=NOW,
        lines_added=3,
        lines_deleted=1,
    )


def _bundle(course_id: str, project_id: str, commits: list[CommitInfo]) -> IngestionMetricBundle:
    return IngestionMetricBundle(
        course_id=course_id,
        project_id=project_id,
        sprint_id="sprint-1",
        commit_frequency=float(len(commits)),
        code_churn=4 * len(commits),
        pr_turnaround_hours=None,
        assigned_story_points=None,
        completion_percent=None,
        commits=commits,
        local_repo_path=None,
        head_sha="abc",
        captured_at=NOW,
    )


@pytest.fixture
def world(override_user_repository):
    """A course with one empty team, a faculty login, and fresh in-memory side repositories."""
    projects = override_user_repository
    users = app.dependency_overrides[get_user_repository]()
    course = projects.create_course("CS480", "Capstone", "001", 2026, "Fall", "u-faculty-1")
    projects.assign_instructor(course.id, "u-faculty-1")
    projects.create_project(
        ProjectRecord(
            id=P,
            project_name="P",
            team_name="Team",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by="u-faculty-1",
            created_at=NOW,
        ),
        [],
    )
    metrics = InMemoryMetricsRepository()
    identities = InMemoryGitIdentityRepository()
    jira = InMemoryJiraIngestionRunRepository()
    app.dependency_overrides[get_metrics_repository] = lambda: metrics
    app.dependency_overrides[get_git_identity_repository] = lambda: identities
    app.dependency_overrides[get_jira_ingestion_repository] = lambda: jira
    login = client.post(
        "/api/v1/auth/login", json={"email": "faculty@sprintsight.edu", "password": "password123"}
    )
    yield SimpleNamespace(
        projects=projects,
        users=users,
        course=course,
        metrics=metrics,
        identities=identities,
        jira=jira,
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    for dependency in (get_metrics_repository, get_git_identity_repository, get_jira_ingestion_repository):
        app.dependency_overrides.pop(dependency, None)


def _join(world, user: UserRecord) -> None:
    """The order the product enforces: create the student, enrol them, then add to the team."""
    world.users.create_user(user)
    assert world.projects.enroll_student(world.course.id, user.id)
    response = client.post(f"/api/v1/projects/{P}/members/{user.id}", headers=world.headers)
    assert response.status_code == 200, response.text


def _stored(world) -> dict[str, str | None]:
    metrics = world.metrics.get_metrics(world.course.id, P, "sprint-1")
    return {commit.sha: commit.student_id for commit in metrics.commits}


def _read(world) -> dict[str, str | None]:
    response = client.get(
        f"/api/v1/repo-ingestion/runs/{P}/sprint-1",
        params={"course_id": world.course.id},
        headers=world.headers,
    )
    assert response.status_code == 200, response.text
    return {commit["sha"]: commit["student_id"] for commit in response.json()["commits"]}


# --------------------------------------------------------------------------- resolver rules
def test_resolver_precedence_and_safety(world) -> None:
    ada = _student(ADA, "ada@school.edu", "Ada Lovelace")
    bob = _student(BOB, "bob@school.edu", "  Bob   Builder ")
    twin_1 = _student(T1, "t1@school.edu", "Sam Smith")
    twin_2 = _student(T2, "t2@school.edu", "sam smith")
    gone = _student(GONE, "gone@school.edu", "Gone Student", active=False)
    for user in (ada, bob, twin_1, twin_2, gone):
        world.users.create_user(user)
    world.projects.set_members(
        P, [ada.id, bob.id, twin_1.id, twin_2.id, gone.id]
    )
    world.identities.upsert_identity(P, "email", "Personal@Gmail.com ", bob.id)
    world.identities.upsert_identity(P, "name", "ghost", ada.id)
    world.identities.upsert_identity(P, "email", "x@y.z", OUTSIDER)

    resolver = build_resolver(P, world.projects, world.users, world.identities)

    assert resolver.resolve("anything", "ADA@School.edu") == ada.id  # tier 2, case-insensitive
    assert resolver.resolve("Ada Lovelace", "12345+ada@users.noreply.github.com") == ada.id  # 3
    assert resolver.resolve("bob builder", None) == bob.id  # whitespace and case trimmed
    assert resolver.resolve("someone", "personal@gmail.com") == bob.id  # tier 1 override
    assert resolver.resolve("Ghost", None) == ada.id  # name override
    assert resolver.resolve("Ada Lovelace", "personal@gmail.com") == bob.id  # override beats name
    assert resolver.resolve("Sam Smith", "n@x.y") is None  # ambiguous name: never guessed
    assert resolver.resolve("Gone Student", "gone@school.edu") is None  # inactive
    assert resolver.resolve("nobody", "nobody@x.y") is None
    assert resolver.resolve("x", "x@y.z") is None  # override to a non-member is ignored
    assert resolver.resolve(None, None) is None


def test_name_that_is_really_an_email_is_not_matched_by_name(world) -> None:
    world.users.create_user(_student(ONE, "other@b.c", "a@b.c"))
    world.projects.set_members(P, [ONE])
    resolver = build_resolver(P, world.projects, world.users, world.identities)
    # git falls back to the email as the "name" when no name is set: that is not a name match
    assert resolver.resolve("a@b.c", "a@b.c") is None


# --------------------------------------------------------------------------- C1
def test_reingesting_for_an_assessment_keeps_existing_attribution(world, monkeypatch) -> None:
    """Before the fix this wiped every student_id (assessments never linked, then replaced the run)."""
    world.metrics.save_metrics(
        _bundle(world.course.id, P, [_commit("c1", "Ada", "a@x.y", ADA)])
    )
    monkeypatch.setattr(
        git_service, "extract_local_commits", lambda path: [_commit("c1", "Ada", "a@x.y")]
    )
    monkeypatch.setattr(git_service, "_repository_head", lambda path: "abc")
    payload = SimpleNamespace(course_id=world.course.id, project_id=P, sprint_id="sprint-1")

    git_service.ingest_github_metrics(payload, Path("."), world.metrics)

    assert _stored(world) == {"c1": ADA}


def test_reingest_with_repositories_relinks_to_current_members(world, monkeypatch) -> None:
    world.users.create_user(_student(ADA, "a@x.y", "Ada"))
    world.projects.set_members(P, [ADA])
    monkeypatch.setattr(
        git_service, "extract_local_commits", lambda path: [_commit("c1", "Ada", "A@X.Y")]
    )
    monkeypatch.setattr(git_service, "_repository_head", lambda path: "abc")
    payload = SimpleNamespace(course_id=world.course.id, project_id=P, sprint_id="sprint-1")

    git_service.ingest_github_metrics(
        payload, Path("."), world.metrics, world.projects, world.users, world.identities
    )

    assert _stored(world) == {"c1": ADA}


# --------------------------------------------------------------------------- order independence
def test_students_added_after_ingestion_are_attributed_on_read_and_stored(world) -> None:
    world.metrics.save_metrics(
        _bundle(
            world.course.id,
            P,
            [
                _commit("c1", "Ada L", "ada@school.edu"),
                _commit("c2", "Ada Lovelace", "ada@users.noreply.github.com"),
                _commit("c3", "Stranger", "x@y.z"),
            ],
        )
    )
    assert _read(world) == {"c1": None, "c2": None, "c3": None}  # nobody on the team yet

    _join(world, _student(ADA, "ada@school.edu", "Ada Lovelace"))

    # add_member refreshed the stored copies (the relink ran in the background task)...
    assert _stored(world) == {"c1": ADA, "c2": ADA, "c3": None}
    # ...and reading resolves the same way.
    assert _read(world) == {"c1": ADA, "c2": ADA, "c3": None}


def test_removing_a_member_unlinks_their_commits(world) -> None:
    _join(world, _student(ADA, "ada@school.edu", "Ada Lovelace"))
    world.metrics.save_metrics(
        _bundle(world.course.id, P, [_commit("c1", "Ada", "ada@school.edu")])
    )
    assert _read(world) == {"c1": ADA}

    response = client.delete(f"/api/v1/projects/{P}/members/{ADA}", headers=world.headers)

    assert response.status_code == 200
    assert _stored(world) == {"c1": None}
    assert _read(world) == {"c1": None}


def test_changing_a_students_email_relinks(world) -> None:
    _join(world, _student(ADA, "old@school.edu", "Ada Lovelace"))
    world.metrics.save_metrics(
        _bundle(world.course.id, P, [_commit("c1", "ada-handle", "new@school.edu")])
    )
    assert _read(world) == {"c1": None}

    # Same person, now with the email their commits use (and a name that does not match).
    world.users.update_user(ADA, "new@school.edu", "Ada Lovelace", Role.STUDENT, True)
    relink_project(P, world.projects, world.users, world.identities, world.metrics, world.jira)

    assert _stored(world) == {"c1": ADA}


# --------------------------------------------------------------------------- alias API
def test_identity_overrides_api(world) -> None:
    _join(world, _student(ADA, "ada@school.edu", "Ada Lovelace"))
    world.metrics.save_metrics(
        _bundle(
            world.course.id,
            P,
            [
                _commit("c1", "JuSt_A_HaNdLe", "9@users.noreply.github.com"),
                _commit("c2", "JuSt_A_HaNdLe", "9@users.noreply.github.com"),
                _commit("c3", "Ada Lovelace", "ada@school.edu"),
            ],
        )
    )

    listing = client.get(f"/api/v1/repo-ingestion/identities/{P}", headers=world.headers)
    assert listing.status_code == 200
    unmatched = listing.json()["unmatched_authors"]
    assert [(u["author"], u["commits"]) for u in unmatched] == [("JuSt_A_HaNdLe", 2)]

    created = client.put(
        f"/api/v1/repo-ingestion/identities/{P}",
        json={"kind": "email", "value": "9@Users.Noreply.GitHub.com", "student_id": ADA},
        headers=world.headers,
    )
    assert created.status_code == 200
    assert created.json()["value"] == "9@users.noreply.github.com"
    assert _stored(world) == {"c1": ADA, "c2": ADA, "c3": ADA}

    outsider = client.put(
        f"/api/v1/repo-ingestion/identities/{P}",
        json={"kind": "name", "value": "x", "student_id": ELSE},
        headers=world.headers,
    )
    assert outsider.status_code == 400
    bad_kind = client.put(
        f"/api/v1/repo-ingestion/identities/{P}",
        json={"kind": "login", "value": "x", "student_id": ADA},
        headers=world.headers,
    )
    assert bad_kind.status_code == 422

    removed = client.delete(
        f"/api/v1/repo-ingestion/identities/{P}/{created.json()['id']}", headers=world.headers
    )
    assert removed.status_code == 200
    assert _stored(world) == {"c1": None, "c2": None, "c3": ADA}


# --------------------------------------------------------------------------- Jira
def test_jira_tickets_are_relinked_by_assignee_name_and_dropped_when_member_leaves(world) -> None:
    _join(world, _student(ADA, "ada@school.edu", "Ada Lovelace"))
    resolver = build_resolver(P, world.projects, world.users, world.identities)
    snapshot = JiraCleanedSnapshot(
        normalization_version="v",
        jira_project_key="K",
        course_id=world.course.id,
        project_id=P,
        sprint_id="sprint-1",
        captured_at=NOW,
        tickets=[
            JiraTicket(ticket_id="K-1", summary="a", assignee="ada lovelace"),
            JiraTicket(ticket_id="K-2", summary="b", assignee="Stranger"),
            JiraTicket(ticket_id="K-3", summary="c", assignee="Left", student_id=LEFT),
        ],
    )

    apply_to_snapshot(snapshot, resolver)

    assert [t.student_id for t in snapshot.tickets] == [ADA, None, None]
