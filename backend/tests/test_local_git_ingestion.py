from pathlib import Path
import subprocess

from app.services.gitlabGithub.service import extract_local_commits


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
