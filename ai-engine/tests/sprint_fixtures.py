"""A sprint shaped like a real one, shared by the judge evidence tests (a module of its own because
mypy cannot import one test module from another)."""

import hashlib
from datetime import UTC, datetime

from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.repo_snapshot import RepoSnapshot, SnapshotFile


def sprint_like_your_data(
    n_commits: int = 311, files_per_commit: int = 10, n_files: int = 201, diff_lines: int = 20
) -> ArtifactBundle:
    """311 commits touching ~10 files each, 201 repository files, 14 tickets."""
    commits = []
    for i in range(n_commits):
        sha = hashlib.sha1(str(i).encode(), usedforsecurity=False).hexdigest()
        commits.append(CommitInfo(
            sha=sha, author=f"student{i % 4}", message=f"commit {i}: change the thing " * 3,
            timestamp=datetime(2026, 1, 1 + i % 28, tzinfo=UTC), lines_added=40, lines_deleted=5,
            files_changed=[
                FileDiff(filename=f"src/pkg{(i + j) % 40}/file_{(i * 7 + j) % 120}.py", lines_added=4, lines_deleted=1,
                         diff="@@ -1,4 +1,5 @@\n" + "+changed line of code here\n" * diff_lines)
                for j in range(files_per_commit)
            ],
        ))
    return ArtifactBundle(
        team_id="t", sprint_id="s", commits=commits,
        jira_tickets=[JiraTicket(ticket_id=f"ENG-{i}", summary="A ticket", status="Done", issue_type="Task") for i in range(14)],
        repo_snapshot=RepoSnapshot(head_sha=commits[0].sha, files=[
            SnapshotFile(path=f"src/pkg{i % 40}/file_{i}.py", size_bytes=5_000, line_count=120, content="code line\n" * 500)
            for i in range(n_files)
        ]),
    )


def many_claims(bundle: ArtifactBundle, n: int = 60) -> str:
    """Claims citing a spread of files and commits, like six dimensions with ~10 citations each."""
    assert bundle.repo_snapshot is not None
    lines = [f"C{i} [testing]: {bundle.repo_snapshot.files[i * 3].path}:L1-L9 | covers the module" for i in range(n // 2)]
    lines += [f"C{n // 2 + i} [cicd]: {bundle.commits[i * 5].sha[:9]} | added a step" for i in range(n // 2)]
    return "\n".join(lines)
