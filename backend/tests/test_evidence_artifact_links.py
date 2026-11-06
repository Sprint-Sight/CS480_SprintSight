import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.dependencies.auth import get_assessment_repository, get_jira_ingestion_repository
from app.main import app
from app.repositories.in_memory import InMemoryJiraIngestionRunRepository
from app.repositories.interfaces import JiraIngestionRunRecord, ProjectRecord
from app.schemas.assessment import (
    AssessmentReport,
    EvidenceDetail,
    JiraCleanedSnapshot,
    JiraTicket,
    RubricDimensionScoreDetail,
    TeamScore,
)
from app.services.artifactViewerService import service as viewer
from app.services.artifactViewerService.service import (
    ArtifactLinkContext,
    build_evidence_link,
    parse_citation_identifier,
    remote_web_url,
    repository_web_url,
)
from app.services.gitlabGithub.service import _parse_patch, read_commit

client = TestClient(app)


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Student One", "-c", "user.email=student@example.com", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def login(email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def student_repo(tmp_path: Path, monkeypatch) -> dict:
    root = tmp_path / "repos"
    repository = root / "team-repo"
    (repository / "src").mkdir(parents=True)
    git(repository, "init")
    (repository / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "Add app")
    first_sha = git(repository, "rev-parse", "HEAD")
    (repository / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text("# Team\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "ENG-7 add subtraction")
    head_sha = git(repository, "rev-parse", "HEAD")
    monkeypatch.setenv("LOCAL_REPOSITORY_ROOT", str(root))
    get_settings.cache_clear()
    yield {"path": repository, "first_sha": first_sha, "head_sha": head_sha}
    get_settings.cache_clear()


@pytest.fixture
def project(override_user_repository, student_repo) -> ProjectRecord:
    record = ProjectRecord(
        id="proj-links",
        project_name="Links",
        team_name="Team Links",
        description=None,
        course_id="cs480",
        course_code="CS480",
        github_repo_url="https://github.com/org/team-repo",
        local_repo_path="team-repo",
        created_by="u-faculty-1",
        created_at=datetime.now(UTC),
        jira_domain="team.atlassian.net",
        jira_project_key="ENG",
    )
    override_user_repository.create_project(record, ["u-student-1"])
    return record


@pytest.fixture
def jira_runs():
    repository = InMemoryJiraIngestionRunRepository()
    captured = datetime(2026, 10, 1, tzinfo=UTC)
    repository.create_run(
        JiraIngestionRunRecord(
            id="run-1",
            course_id="cs480",
            project_id="proj-links",
            sprint_id="sp1",
            jira_project_key="ENG",
            jql="project = ENG",
            raw_bucket="b",
            raw_object_key="k",
            issue_count=1,
            captured_at=captured,
            processing_status="completed",
            cleaned_snapshot=JiraCleanedSnapshot(
                normalization_version="v1",
                jira_project_key="ENG",
                course_id="cs480",
                project_id="proj-links",
                sprint_id="sp1",
                captured_at=captured,
                tickets=[JiraTicket(ticket_id="ENG-7", summary="Add subtraction", status="Done")],
            ),
        )
    )
    app.dependency_overrides[get_jira_ingestion_repository] = lambda: repository
    yield repository
    app.dependency_overrides.pop(get_jira_ingestion_repository, None)


def save_report(
    rubric_scores: dict[str, RubricDimensionScoreDetail], project_id: str = "proj-links"
) -> str:
    report = AssessmentReport(
        report_id="rpt-links",
        model_name="m",
        mode="ai",
        course_id="cs480",
        project_id=project_id,
        sprint_id="sp1",
        generated_at=datetime.now(UTC),
        rubric_weights={},
        team_score=TeamScore(score=80, rationale="ok"),
        individual_scores=[],
        rubric_scores=rubric_scores,
        recommendations=[],
    )
    app.dependency_overrides[get_assessment_repository]().save_report(report)
    return report.report_id


# ── Link building ─────────────────────────────────────────────────────────


def test_repository_web_url_normalizes_supported_hosts() -> None:
    assert repository_web_url("https://github.com/org/repo.git/") == (
        "https://github.com/org/repo",
        "github",
    )
    assert repository_web_url("https://gitlab.com/group/repo") == (
        "https://gitlab.com/group/repo",
        "gitlab",
    )
    assert repository_web_url("https://bitbucket.org/team/repo.git") == (
        "https://bitbucket.org/team/repo",
        "bitbucket",
    )
    assert repository_web_url("https://example.com/org/repo") == (None, None)
    assert repository_web_url(None) == (None, None)


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://bitbucket.org/team/repo.git", "https://bitbucket.org/team/repo"),
        ("https://alice@bitbucket.org/team/repo.git", "https://bitbucket.org/team/repo"),
        ("https://x-access-token:secret@github.com/org/repo.git", "https://github.com/org/repo"),
        ("git@github.com:org/repo.git", "https://github.com/org/repo"),
        ("ssh://git@gitlab.com:22/group/sub/repo.git", "https://gitlab.com/group/sub/repo"),
        ("/srv/repos/team-repo", None),
        ("C:\\repos\\team-repo", None),
        (None, None),
    ],
)
def test_remote_web_url_drops_credentials_and_local_paths(remote, expected) -> None:
    assert remote_web_url(remote) == expected


def test_bitbucket_link_formats() -> None:
    context = ArtifactLinkContext(
        project_id="p1",
        repository_url="https://bitbucket.org/team/repo",
        repository_source="bitbucket",
    )
    file_link = build_evidence_link(
        "x",
        EvidenceDetail(
            identifier="a.py:L3-L5",
            kind="file_lines",
            file_path="a.py",
            line_start=3,
            line_end=5,
            commit_sha="abc1234",
        ),
        context,
    )
    assert file_link.external_url == "https://bitbucket.org/team/repo/src/abc1234/a.py#lines-3:5"
    assert file_link.external_source == "bitbucket"
    commit_link = build_evidence_link(
        "x", EvidenceDetail(identifier="abc1234", kind="commit", commit_sha="abc1234"), context
    )
    assert commit_link.external_url == "https://bitbucket.org/team/repo/commits/abc1234"


def test_structured_citations_link_to_github_jira_and_viewer() -> None:
    context = ArtifactLinkContext(
        project_id="p1",
        repository_url="https://github.com/org/repo",
        repository_source="github",
        jira_base_url="https://team.atlassian.net",
        has_local_repository=True,
        known_tickets={"ENG-7"},
    )
    file_link = build_evidence_link(
        "x",
        EvidenceDetail(
            identifier="src/app.py:L10-L24@abc1234",
            kind="diff_lines",
            file_path="src/app.py",
            line_start=10,
            line_end=24,
            commit_sha="abc1234def",
        ),
        context,
    )
    assert (
        file_link.external_url == "https://github.com/org/repo/blob/abc1234def/src/app.py#L10-L24"
    )
    assert (
        file_link.viewer_path
        == "/artifacts/projects/p1/file?path=src%2Fapp.py&ref=abc1234def&start=10&end=24"
    )
    assert file_link.external_source == "github"

    commit_link = build_evidence_link(
        "x", EvidenceDetail(identifier="abc1234", kind="commit", commit_sha="abc1234def"), context
    )
    assert commit_link.external_url == "https://github.com/org/repo/commit/abc1234def"
    assert commit_link.viewer_path == "/artifacts/projects/p1/commits/abc1234def"

    ticket_link = build_evidence_link(
        "x", EvidenceDetail(identifier="ENG-7", kind="ticket"), context
    )
    assert ticket_link.external_url == "https://team.atlassian.net/browse/ENG-7"
    assert ticket_link.viewer_path == "/artifacts/projects/p1/tickets/ENG-7"
    assert ticket_link.external_source == "jira"


def test_gitlab_line_anchor_format() -> None:
    context = ArtifactLinkContext(
        project_id="p1", repository_url="https://gitlab.com/g/r", repository_source="gitlab"
    )
    link = build_evidence_link(
        "x",
        EvidenceDetail(
            identifier="a.py:L3-L5",
            kind="file_lines",
            file_path="a.py",
            line_start=3,
            line_end=5,
            commit_sha="abc1234",
        ),
        context,
    )
    assert link.external_url == "https://gitlab.com/g/r/-/blob/abc1234/a.py#L3-5"
    assert link.viewer_path is None  # no local repository to read from


def test_plain_text_citations_are_parsed_conservatively() -> None:
    context = ArtifactLinkContext(
        project_id="p1",
        known_paths={"src/app.py", "README.md"},
        jira_project_key="ENG",
    )
    line_target = parse_citation_identifier("app.py:L2-L1", context)
    assert (line_target.file_path, line_target.line_start, line_target.line_end) == (
        "src/app.py",
        1,
        2,
    )
    assert parse_citation_identifier("ENG-12", context).ticket_id == "ENG-12"
    assert parse_citation_identifier("commit 9f3c2a1", context).commit_sha == "9f3c2a1"
    assert parse_citation_identifier("Updated README.md", context).file_path == "README.md"
    # Look-alikes that must stay unlinked.
    assert parse_citation_identifier("UTF-8 encoding", context) is None
    assert parse_citation_identifier("1234567 lines", context) is None
    assert parse_citation_identifier("defaced", context) is None
    assert parse_citation_identifier("Node.js", context) is None
    assert parse_citation_identifier("completion_percent=80", context) is None


# ── Git readers ───────────────────────────────────────────────────────────


def test_parse_patch_handles_added_renamed_and_binary_files() -> None:
    patch = (
        "diff --git a/new.py b/new.py\nnew file mode 100644\nindex 0000000..1\n--- /dev/null\n+++ b/new.py\n"
        "@@ -0,0 +1,2 @@\n+a\n+b\n"
        "diff --git a/old.py b/moved.py\nsimilarity index 90%\nrename from old.py\nrename to moved.py\n"
        "--- a/old.py\n+++ b/moved.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/logo.png b/logo.png\nnew file mode 100644\nBinary files /dev/null and b/logo.png differ\n"
    )
    files = {file["filename"]: file for file in _parse_patch(patch)}
    assert files["new.py"]["change_type"] == "added"
    assert (files["new.py"]["lines_added"], files["new.py"]["lines_deleted"]) == (2, 0)
    assert files["new.py"]["diff"].startswith("@@ -0,0 +1,2 @@")
    assert files["moved.py"]["change_type"] == "renamed"
    assert (files["moved.py"]["lines_added"], files["moved.py"]["lines_deleted"]) == (1, 1)
    assert files["logo.png"]["diff"] is None


def test_read_commit_returns_metadata_and_diffs(student_repo) -> None:
    commit = read_commit(student_repo["path"], student_repo["head_sha"][:7], 10000, 100000)
    assert commit["commit_sha"] == student_repo["head_sha"]
    assert commit["parent_shas"] == [student_repo["first_sha"]]
    assert commit["message"] == "ENG-7 add subtraction"
    assert commit["author"] == "Student One"
    files = {file["filename"]: file for file in commit["files_changed"]}
    assert files["README.md"]["change_type"] == "added"
    assert "+def sub(a, b):" in files["src/app.py"]["diff"]
    assert commit["lines_added"] == 5


# ── Endpoints ─────────────────────────────────────────────────────────────


def test_report_evidence_endpoint_links_structured_and_legacy_citations(
    project, student_repo, jira_runs
) -> None:
    head = student_repo["head_sha"]
    report_id = save_report(
        {
            "code_quality": RubricDimensionScoreDetail(
                score=70,
                evidence_citations=[
                    f"src/app.py:L5-L6@{head[:7]} — Subtraction is a small pure function.",
                    "README.md — Instructor added this by hand.",
                ],
                evidence_details=[
                    EvidenceDetail(
                        identifier=f"src/app.py:L5-L6@{head[:7]}",
                        reason="Subtraction is a small pure function.",
                        kind="diff_lines",
                        file_path="src/app.py",
                        line_start=5,
                        line_end=6,
                        commit_sha=head,
                    )
                ],
            ),
            "requirements": RubricDimensionScoreDetail(
                score=80,
                evidence_citations=[
                    "ENG-7 — Ticket closed with the change.",
                    "Good teamwork overall",
                ],
            ),
        }
    )

    response = client.get(
        f"/api/v1/assessments/reports/{report_id}/evidence",
        headers=login("faculty@sprintsight.edu"),
    )

    assert response.status_code == 200
    dimensions = response.json()["dimensions"]
    structured, legacy_file = dimensions["code_quality"]
    assert (
        structured["external_url"]
        == f"https://github.com/org/team-repo/blob/{head}/src/app.py#L5-L6"
    )
    assert structured["citation"].startswith("src/app.py:L5-L6")
    assert legacy_file["target"]["file_path"] == "README.md"
    # No commit recorded: pinned to the clone's HEAD, not the remote's moving HEAD.
    assert legacy_file["external_url"] == f"https://github.com/org/team-repo/blob/{head}/README.md"

    ticket, prose = dimensions["requirements"]
    assert ticket["external_url"] == "https://team.atlassian.net/browse/ENG-7"
    assert ticket["viewer_path"] == "/artifacts/projects/proj-links/tickets/ENG-7"
    assert (
        prose["target"] is None and prose["viewer_path"] is None and prose["external_url"] is None
    )

    # The viewer paths are directly fetchable.
    file_view = client.get(
        f"/api/v1{structured['viewer_path']}", headers=login("faculty@sprintsight.edu")
    )
    assert file_view.status_code == 200
    body = file_view.json()
    assert (body["highlight_start"], body["highlight_end"]) == (5, 6)
    assert body["lines"][4] == {"number": 5, "text": "def sub(a, b):"}
    assert body["commit_sha"] == head


def test_file_view_pins_commit_and_rejects_bad_input(project, student_repo) -> None:
    headers = login("faculty@sprintsight.edu")
    old = client.get(
        "/api/v1/artifacts/projects/proj-links/file",
        params={"path": "src/app.py", "ref": student_repo["first_sha"]},
        headers=headers,
    )
    assert old.status_code == 200
    assert old.json()["total_lines"] == 2
    assert old.json()["highlight_start"] is None

    for params in (
        {"path": "../secrets.txt"},
        {"path": "src/app.py", "ref": "main"},
        {"path": "src/app.py", "ref": "--output=x"},
        {"path": "missing.py"},
    ):
        response = client.get(
            "/api/v1/artifacts/projects/proj-links/file", params=params, headers=headers
        )
        assert response.status_code == 404, params


def test_large_file_is_windowed_around_highlight(project, student_repo, monkeypatch) -> None:
    monkeypatch.setattr(viewer, "VIEWER_MAX_FILE_LINES", 50)
    monkeypatch.setattr(viewer, "VIEWER_CONTEXT_LINES", 5)
    repository = student_repo["path"]
    (repository / "big.py").write_text(
        "".join(f"x{n} = {n}\n" for n in range(1, 301)), encoding="utf-8"
    )
    git(repository, "add", ".")
    git(repository, "commit", "-m", "Add big file")

    response = client.get(
        "/api/v1/artifacts/projects/proj-links/file",
        params={"path": "big.py", "start": 100, "end": 102},
        headers=login("faculty@sprintsight.edu"),
    )

    body = response.json()
    assert body["truncated"] is True
    assert (body["first_line"], body["last_line"], body["total_lines"]) == (95, 107, 300)
    assert body["lines"][0] == {"number": 95, "text": "x95 = 95"}


def test_commit_and_ticket_views(project, student_repo, jira_runs) -> None:
    headers = login("student@sprintsight.edu")  # a project member

    commit = client.get(
        f"/api/v1/artifacts/projects/proj-links/commits/{student_repo['head_sha']}", headers=headers
    )
    assert commit.status_code == 200
    assert (
        commit.json()["external_url"]
        == f"https://github.com/org/team-repo/commit/{student_repo['head_sha']}"
    )
    assert (
        client.get(
            "/api/v1/artifacts/projects/proj-links/commits/deadbeef1", headers=headers
        ).status_code
        == 404
    )

    ticket = client.get("/api/v1/artifacts/projects/proj-links/tickets/ENG-7", headers=headers)
    assert ticket.status_code == 200
    assert ticket.json()["ticket"]["summary"] == "Add subtraction"
    assert ticket.json()["external_url"] == "https://team.atlassian.net/browse/ENG-7"
    assert (
        client.get(
            "/api/v1/artifacts/projects/proj-links/tickets/ENG-99", headers=headers
        ).status_code
        == 404
    )


def test_clone_remote_is_used_when_project_has_no_saved_url(
    override_user_repository, student_repo
) -> None:
    git(
        student_repo["path"],
        "remote",
        "add",
        "origin",
        "https://alice@bitbucket.org/team/team-repo.git",
    )
    override_user_repository.create_project(
        ProjectRecord(
            id="proj-remote",
            project_name="Remote",
            team_name="Remote",
            description=None,
            course_id="cs480",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="team-repo",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    head = student_repo["head_sha"]

    commit = client.get(
        f"/api/v1/artifacts/projects/proj-remote/commits/{head}",
        headers=login("faculty@sprintsight.edu"),
    )

    assert commit.json()["external_url"] == f"https://bitbucket.org/team/team-repo/commits/{head}"
    assert commit.json()["external_source"] == "bitbucket"


def test_students_outside_the_project_are_refused(override_user_repository, student_repo) -> None:
    override_user_repository.create_project(
        ProjectRecord(
            id="proj-other",
            project_name="Other",
            team_name="Other",
            description=None,
            course_id="cs480",
            course_code="CS480",
            github_repo_url=None,
            local_repo_path="team-repo",
            created_by="u-faculty-1",
            created_at=datetime.now(UTC),
        ),
        [],
    )
    report_id = save_report({}, project_id="proj-other")
    headers = login("student@sprintsight.edu")

    assert (
        client.get(
            "/api/v1/artifacts/projects/proj-other/file",
            params={"path": "README.md"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/assessments/reports/{report_id}/evidence", headers=headers).status_code
        == 403
    )
