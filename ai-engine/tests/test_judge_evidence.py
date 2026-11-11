"""The judge reads only the evidence its claims cite, so a real sprint fits its context."""

import hashlib
import json
from datetime import UTC, datetime

from evaluation.judges.evidence import build_judge_bundle, judge_bundle_json
from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.repo_snapshot import RepoSnapshot, SnapshotFile

SHA_A = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
SHA_B = "b2c3d4e5f60718293a4b5c6d7e8f9012345678a1"


def commit(sha: str, filename: str, diff: str = "BIG DIFF " * 50) -> CommitInfo:
    return CommitInfo(
        sha=sha, author="alice", message="work", timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        lines_added=10, lines_deleted=2,
        files_changed=[FileDiff(filename=filename, lines_added=10, lines_deleted=2, diff=diff)],
    )


def make_bundle() -> ArtifactBundle:
    return ArtifactBundle(
        team_id="team-a", sprint_id="s1",
        commits=[commit(SHA_A, "src/auth.py"), commit(SHA_B, "src/other.py")],
        jira_tickets=[JiraTicket(ticket_id="AUTH-2", summary="Auth tests", status="Done", issue_type="Task")],
        repo_snapshot=RepoSnapshot(head_sha=SHA_A, files=[
            SnapshotFile(path="src/auth.py", size_bytes=900, line_count=30, content="AUTH CONTENT " * 40),
            SnapshotFile(path="src/other.py", size_bytes=900, line_count=30, content="OTHER CONTENT " * 40),
        ]),
        project_context_documents=[{"filename": "brief.pdf", "text": "BACKGROUND " * 500}],
        instructor_expectations="Expect tests.",
    )


def test_every_commit_ticket_and_file_is_listed_so_existence_can_be_checked() -> None:
    judged = build_judge_bundle(make_bundle(), "AUTH-2 | ticket is done")

    assert [c["sha"] for c in judged["commits"]] == [SHA_A, SHA_B]
    assert [t["ticket_id"] for t in judged["jira_tickets"]] == ["AUTH-2"]
    assert [f["path"] for f in judged["repo_snapshot"]["files"]] == ["src/auth.py", "src/other.py"]
    assert judged["commits"][0]["files_changed"][0]["filename"] == "src/auth.py"
    assert judged["commits"][0]["author"] == "alice" and judged["commits"][0]["lines_added"] == 10


def test_a_diff_is_included_only_for_a_commit_the_claims_cite() -> None:
    judged = build_judge_bundle(make_bundle(), f"{SHA_A[:7]} | added the auth module")

    assert "diff" in judged["commits"][0]["files_changed"][0]
    assert "diff" not in judged["commits"][1]["files_changed"][0]


def test_a_cited_file_is_shown_at_head_not_through_every_commit_that_touched_it() -> None:
    # A claim about `src/other.py:L1-L5` is about the file as it is now; the snapshot has it, so
    # no commit's diff is needed (a file touched by 30 commits used to bring in 30 diffs).
    judged = build_judge_bundle(make_bundle(), "src/other.py:L1-L5 | validation helper")

    assert "diff" not in judged["commits"][1]["files_changed"][0]
    by_path = {f["path"]: f for f in judged["repo_snapshot"]["files"]}
    assert "content" in by_path["src/other.py"]


def test_a_cited_file_missing_from_the_snapshot_falls_back_to_the_diffs_that_touched_it() -> None:
    bundle = make_bundle().model_copy(update={"repo_snapshot": RepoSnapshot(head_sha=SHA_A, files=[])})

    judged = build_judge_bundle(bundle, "src/other.py:L1-L5 | validation helper")

    assert "diff" in judged["commits"][1]["files_changed"][0]
    assert "diff" not in judged["commits"][0]["files_changed"][0]


def test_file_contents_are_included_only_for_a_cited_file() -> None:
    judged = build_judge_bundle(make_bundle(), "src/auth.py:L10-L20 | token check")

    by_path = {f["path"]: f for f in judged["repo_snapshot"]["files"]}
    assert "content" in by_path["src/auth.py"]
    assert "content" not in by_path["src/other.py"]


def test_a_cited_file_is_found_by_its_bare_name_too() -> None:
    judged = build_judge_bundle(make_bundle(), "auth.py | the module")
    assert "content" in {f["path"]: f for f in judged["repo_snapshot"]["files"]}["src/auth.py"]


def test_windows_style_paths_in_claims_still_match() -> None:
    judged = build_judge_bundle(make_bundle(), "src\\auth.py:L1-L2 | x")
    assert "content" in {f["path"]: f for f in judged["repo_snapshot"]["files"]}["src/auth.py"]


def test_background_documents_and_instructor_text_are_never_sent() -> None:
    judged = build_judge_bundle(make_bundle(), "AUTH-2 | x")
    text = json.dumps(judged)

    assert "BACKGROUND" not in text and "Expect tests" not in text
    assert "project_context_documents" not in judged and "instructor_expectations" not in judged


def test_a_bundle_without_a_snapshot_is_handled() -> None:
    bundle = make_bundle().model_copy(update={"repo_snapshot": None})
    assert build_judge_bundle(bundle, "AUTH-2 | x")["repo_snapshot"] is None


def test_a_realistic_sprint_shrinks_from_hundreds_of_thousands_of_tokens_to_a_fitting_prompt() -> None:
    # 150 commits with 8 KB diffs, 200 repo files of 12 KB and a long brief: a few hundred thousand tokens
    # whole (a real sprint measured ~708K), which can never fit a 49K-token judge.
    commits = [
        commit(hashlib.sha1(str(i).encode(), usedforsecurity=False).hexdigest(), f"src/module_{i % 50}.py", diff="d" * 8_000)
        for i in range(150)
    ]
    files = [SnapshotFile(path=f"src/module_{i}.py", size_bytes=12_000, line_count=300, content="c" * 12_000)
             for i in range(200)]
    bundle = ArtifactBundle(
        team_id="t", sprint_id="s", commits=commits,
        repo_snapshot=RepoSnapshot(head_sha=commits[0].sha, files=files),
        project_context_documents=[{"filename": "brief", "text": "x" * 400_000}],
    )
    claims = f"C1 [testing]: src/module_3.py:L10-L20 | covered\nC2 [cicd]: {commits[7].sha[:7]} | workflow added"

    whole = len(bundle.model_dump_json()) // 4
    judged = len(judge_bundle_json(bundle, claims)) // 4

    assert whole > 500_000              # the case that failed with JudgeContextTooSmall
    assert judged < whole / 10          # an order of magnitude smaller
    assert judged < 49_152 * 0.85       # and now inside the judge's context window
