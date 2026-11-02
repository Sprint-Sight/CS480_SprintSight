from datetime import datetime, timezone
from pathlib import Path
import subprocess

from app.repositories.interfaces import UserRecord
from app.schemas.assessment import CommitInfo
from app.schemas.auth import Role
from app.services.gitlabGithub.service import (
    _is_noise_path,
    _link_commit_authors_to_students,
    collect_repository_snapshot,
    extract_local_commits,
)


class StubProjectRepository:
    def list_member_ids(self, project_id: str) -> list[str]:
        assert project_id == "project-1"
        return ["student-1", "instructor-1"]


class StubUserRepository:
    def __init__(self, users: list[UserRecord]) -> None:
        self.users = {user.email.lower(): user for user in users}

    def get_by_email(self, email: str) -> UserRecord | None:
        return self.users.get(email.lower())


def git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def test_extract_local_commits_includes_file_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "student-repo"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.name", "Student One")
    git(repository, "config", "user.email", "student@example.com")

    (repository / "README.md").write_text("first line\n", encoding="utf-8")
    git(repository, "add", "README.md")
    git(repository, "commit", "-m", "Add README")

    (repository / "README.md").write_text("first line\nsecond line\n", encoding="utf-8")
    (repository / "app.py").write_text("print('hello')\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "Add implementation")

    commits = extract_local_commits(repository)

    assert len(commits) == 2
    implementation = next(
        commit for commit in commits if commit.message.startswith("Add implementation")
    )
    initial = next(commit for commit in commits if commit.message.startswith("Add README"))
    assert implementation.sha
    assert implementation.author == "Student One"
    assert implementation.author_email == "student@example.com"
    assert implementation.student_id is None
    assert implementation.timestamp.tzinfo is not None
    assert implementation.lines_added == 2
    assert implementation.lines_deleted == 0
    assert {file.filename for file in implementation.files_changed} == {"README.md", "app.py"}
    assert all(
        file.change_type in {"added", "modified", "deleted", "renamed"}
        for file in implementation.files_changed
    )
    assert initial.files_changed[0].filename == "README.md"
    assert initial.files_changed[0].change_type == "added"
    assert all(".git" not in file.filename for commit in commits for file in commit.files_changed)
    readme_change = next(
        file for file in implementation.files_changed if file.filename == "README.md"
    )
    assert readme_change.diff is not None
    assert "+second line" in readme_change.diff
    assert readme_change.diff_truncated is False


def test_link_commit_authors_only_to_active_project_students() -> None:
    timestamp = datetime.now(timezone.utc)
    commits = [
        CommitInfo(sha="student", author="Student One", author_email=" Student@Example.com ", message="", timestamp=timestamp),
        CommitInfo(sha="instructor", author="Instructor", author_email="instructor@example.com", message="", timestamp=timestamp),
        CommitInfo(sha="unknown", author="Unknown", author_email="unknown@example.com", message="", timestamp=timestamp),
    ]
    users = StubUserRepository([
        UserRecord("student-1", "student@example.com", "Student One", Role.STUDENT, "hash"),
        UserRecord("instructor-1", "instructor@example.com", "Instructor", Role.INSTRUCTOR, "hash"),
    ])

    _link_commit_authors_to_students(commits, "project-1", StubProjectRepository(), users)

    assert commits[0].student_id == "student-1"
    assert commits[1].student_id is None
    assert commits[2].student_id is None


def test_diffs_are_capped_and_skipped_for_noise_files(tmp_path: Path, monkeypatch) -> None:
    from app.services.gitlabGithub import service

    monkeypatch.setattr(service, "DIFF_MAX_CHARS_PER_FILE", 200)
    repository = tmp_path / "student-repo"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.name", "Student One")
    git(repository, "config", "user.email", "student@example.com")
    big_file = "".join(f"line_{n} = {n}\n" for n in range(200))
    (repository / "big.py").write_text(big_file, encoding="utf-8")
    (repository / "package-lock.json").write_text("{}\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "Add files")

    files = {file.filename: file for file in extract_local_commits(repository)[0].files_changed}

    assert files["big.py"].diff_truncated is True
    assert 0 < len(files["big.py"].diff or "") <= 200
    assert files["package-lock.json"].diff is None
    assert files["package-lock.json"].diff_truncated is False


def test_noise_paths_match_whole_segments() -> None:
    assert _is_noise_path("web/node_modules/react/index.js")
    assert _is_noise_path("yarn.lock")
    assert not _is_noise_path("src/layout/Header.tsx")
    assert not _is_noise_path("src/about/Page.tsx")


def test_collect_repository_snapshot_reads_head_without_checkout(tmp_path: Path) -> None:
    repository = tmp_path / "student-repo"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.name", "Student One")
    git(repository, "config", "user.email", "student@example.com")
    (repository / "src").mkdir()
    (repository / "src" / "app.py").write_text("print('v1')\n", encoding="utf-8")
    (repository / "logo.png").write_bytes(b"\x89PNG\x00\x00binary")
    (repository / "node_modules").mkdir()
    (repository / "node_modules" / "dep.js").write_text("x\n", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "First")
    first_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True,
    ).stdout.strip()
    (repository / "src" / "app.py").write_text("print('v2')\nprint('more')\n", encoding="utf-8")
    git(repository, "commit", "-am", "Second")

    snapshot = collect_repository_snapshot(repository, first_sha)

    assert snapshot["head_sha"] == first_sha
    assert snapshot["omitted_noise_files"] == 1
    files = {file["path"]: file for file in snapshot["files"]}
    assert set(files) == {"src/app.py", "logo.png"}
    assert files["src/app.py"]["content"] == "print('v1')\n"
    assert files["src/app.py"]["line_count"] == 1
    assert files["logo.png"]["content"] is None
    working_copy = (repository / "src" / "app.py").read_text(encoding="utf-8")
    assert working_copy.startswith("print('v2')")
