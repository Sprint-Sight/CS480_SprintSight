"""The eval-bundle export must produce the bundle a live assessment sends the AI engine."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.repositories.interfaces import IngestionMetricBundle, JiraIngestionRunRecord
from app.schemas.assessment import CommitInfo, JiraCleanedSnapshot, JiraIssueChange, JiraTicket
from app.services.middleManService.service import build_assessment_payload
from scripts import export_eval_bundles as export

NOW = datetime(2024, 10, 1, 12, 0, tzinfo=UTC)


def _metrics(project_id: str = "p1", sprint_id: str = "sprint-1") -> IngestionMetricBundle:
    return IngestionMetricBundle(
        course_id="c1",
        project_id=project_id,
        sprint_id=sprint_id,
        commit_frequency=1.0,
        code_churn=3,
        pr_turnaround_hours=None,
        assigned_story_points=None,
        completion_percent=None,
        commits=[CommitInfo(sha="a" * 40, author="Alice", message="init", timestamp=NOW)],
        local_repo_path="/app/repo/team",
        head_sha="a" * 40,
        captured_at=NOW,
    )


def _jira_run(captured_at: datetime, summary: str) -> JiraIngestionRunRecord:
    ticket = JiraTicket(
        ticket_id="T-1",
        summary=summary,
        changelog=[JiraIssueChange(created=NOW)],
    )
    snapshot = JiraCleanedSnapshot(
        normalization_version="v1",
        jira_project_key="T",
        course_id="c1",
        project_id="p1",
        sprint_id="sprint-1",
        captured_at=captured_at,
        tickets=[ticket],
    )
    return JiraIngestionRunRecord(
        id=summary,
        course_id="c1",
        project_id="p1",
        sprint_id="sprint-1",
        jira_project_key="T",
        jql="",
        raw_bucket="b",
        raw_object_key="k",
        issue_count=1,
        captured_at=captured_at,
        cleaned_snapshot=snapshot,
    )


class FakeJira:
    def __init__(self, runs):
        self.runs = runs

    def list_runs(self, project_id, sprint_id):
        return [r for r in self.runs if r.project_id == project_id and r.sprint_id == sprint_id]

    def list_project_runs(self, project_id):
        return [r for r in self.runs if r.project_id == project_id]


def test_bundle_has_exactly_the_fields_the_ai_engine_builds() -> None:
    snapshot = {"head_sha": "a" * 40, "files": [{"path": "README.md", "content": "hi"}]}
    payload = build_assessment_payload(_metrics(), {}, None, [], [], snapshot)

    bundle = export.bundle_from_payload(payload)

    assert tuple(bundle) == export.BUNDLE_FIELDS
    assert bundle["team_id"] == "p1"  # the AI engine uses the project id as the team id
    assert bundle["sprint_id"] == "sprint-1"
    assert bundle["repo_snapshot"] == snapshot
    assert bundle["peer_evaluations"] == []
    assert bundle["instructor_expectations"] == "No instructor guidance provided."
    json.dumps(bundle)  # JSON-ready, as written to disk


def test_jira_tickets_are_the_latest_snapshot_without_changelogs() -> None:
    older = _jira_run(datetime(2024, 9, 1, tzinfo=UTC), "older")
    newer = _jira_run(datetime(2024, 9, 2, tzinfo=UTC), "newer")

    tickets = export.latest_jira_tickets(FakeJira([older, newer]), "p1", "sprint-1")

    assert [t["summary"] for t in tickets] == ["newer"]
    assert "changelog" not in tickets[0]


def test_build_live_payload_collects_what_run_assessment_job_collects(monkeypatch) -> None:
    from app.services import documentsService, gitlabGithub

    calls = {}
    monkeypatch.setattr(
        gitlabGithub.service, "resolve_local_repository_path", lambda path: Path("/repo") / path
    )

    def fake_ingest(request, repository_path, metrics_repository):
        calls["ingest"] = (request.project_id, request.sprint_id, repository_path)
        return _metrics()

    def fake_snapshot(repository_path, revision):
        calls["snapshot"] = (repository_path, revision)
        return {"head_sha": revision, "files": []}

    monkeypatch.setattr(gitlabGithub.service, "ingest_github_metrics", fake_ingest)
    monkeypatch.setattr(gitlabGithub.service, "collect_repository_snapshot", fake_snapshot)
    monkeypatch.setattr(
        documentsService.service,
        "collect_project_context_documents",
        lambda project_id, repo, storage: [{"filename": "brief.md", "text": "brief"}],
    )
    repos = {
        "metrics": object(),
        "jira": FakeJira([_jira_run(NOW, "ticket")]),
        "manual": SimpleNamespace(get=lambda course, project, sprint: "Ship the MVP."),
        "documents": object(),
    }
    ref = export.SprintRef("c1", "p1", "sprint-1", "team_sprint-1")
    project = SimpleNamespace(team_name="Team", local_repo_path="team")

    payload = export.build_live_payload(ref, project, repos, storage=object())

    assert calls["ingest"] == ("p1", "sprint-1", Path("/repo/team"))
    assert calls["snapshot"] == (Path("/repo/team"), "a" * 40)  # the ingested HEAD
    assert payload["instructor_expectations"] == "Ship the MVP."
    assert [t["summary"] for t in payload["jira_tickets"]] == ["ticket"]
    assert payload["project_context_documents"] == [{"filename": "brief.md", "text": "brief"}]
    assert payload["repo_snapshot"] == {"head_sha": "a" * 40, "files": []}


def test_a_failed_snapshot_degrades_to_history_only_like_a_live_assessment(monkeypatch) -> None:
    from app.services import documentsService, gitlabGithub

    monkeypatch.setattr(gitlabGithub.service, "resolve_local_repository_path", lambda p: Path(p))
    monkeypatch.setattr(gitlabGithub.service, "ingest_github_metrics", lambda *a: _metrics())

    def broken(*args):
        raise RuntimeError("git failed")

    monkeypatch.setattr(gitlabGithub.service, "collect_repository_snapshot", broken)
    monkeypatch.setattr(documentsService.service, "collect_project_context_documents", broken)
    repos = {
        "metrics": object(),
        "jira": FakeJira([]),
        "manual": SimpleNamespace(get=lambda *a: None),
        "documents": object(),
    }

    payload = export.build_live_payload(
        export.SprintRef("c1", "p1", "sprint-1", "x"),
        SimpleNamespace(team_name="Team", local_repo_path="team"),
        repos,
        storage=object(),
    )

    assert payload["repo_snapshot"] is None
    assert payload["project_context_documents"] == []
    assert payload["commits"]


def test_a_project_without_a_repository_is_skipped() -> None:
    with pytest.raises(LookupError, match="no local repository"):
        export.build_live_payload(
            export.SprintRef("c1", "p1", "sprint-1", "x"),
            SimpleNamespace(team_name="Team", local_repo_path=None),
            {},
            storage=None,
        )


def _course(course_id: str, code: str = "CS203"):
    return SimpleNamespace(id=course_id, code=code, section="G1", year=2024, term="Term 1")


def _project(project_id: str, team_name: str):
    return SimpleNamespace(id=project_id, team_name=team_name)


def _run(project_id: str, sprint_id: str):
    return SimpleNamespace(project_id=project_id, sprint_id=sprint_id)


def test_course_selection_exports_every_project_and_sprint_with_readable_names() -> None:
    projects = SimpleNamespace(
        list_courses=lambda: [_course("c1"), _course("c2", "CS999")],
        list_projects=lambda course_id: [_project("p2", "Esports TMS"), _project("p1", "FTMS")],
    )
    jira = FakeJira(
        [
            _run("p1", "sprint-2"),
            _run("p1", "sprint-1"),
            _run("p1", "sprint-1"),
            _run("p2", "sprint-1"),
        ]
    )

    refs = export.sprints_for_course("cs203", projects, jira)

    assert [(r.project_id, r.sprint_id, r.output_name) for r in refs] == [
        ("p2", "sprint-1", "esports_tms_sprint-1"),
        ("p1", "sprint-1", "ftms_sprint-1"),
        ("p1", "sprint-2", "ftms_sprint-2"),
    ]
    assert {r.course_id for r in refs} == {"c1"}


def test_an_ambiguous_course_code_asks_for_an_id() -> None:
    projects = SimpleNamespace(list_courses=lambda: [_course("c1"), _course("c2")])

    with pytest.raises(LookupError, match="ambiguous"):
        export.sprints_for_course("CS203", projects, FakeJira([]))


def test_export_writes_bundles_and_skips_existing_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        export,
        "build_live_payload",
        lambda ref, project, repos, storage: build_assessment_payload(
            _metrics(ref.project_id, ref.sprint_id), {}, None, [], [], None
        ),
    )
    repos = {
        "projects": SimpleNamespace(get_project=lambda pid: None if pid == "gone" else object())
    }
    refs = [
        export.SprintRef("c1", "p1", "sprint-1", "ftms_sprint-1"),
        export.SprintRef("c1", "gone", "sprint-1", "missing"),
    ]

    assert export.export(refs, repos, None, tmp_path, overwrite=False) == 1  # one sprint failed
    written = json.loads((tmp_path / "ftms_sprint-1.json").read_text(encoding="utf-8"))
    assert written["team_id"] == "p1" and written["sprint_id"] == "sprint-1"
    assert not (tmp_path / "missing.json").exists()

    (tmp_path / "ftms_sprint-1.json").write_text("{}", encoding="utf-8")
    export.export(refs[:1], repos, None, tmp_path, overwrite=False)
    assert (tmp_path / "ftms_sprint-1.json").read_text(encoding="utf-8") == "{}"  # kept
