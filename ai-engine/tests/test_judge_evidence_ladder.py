"""The judge's evidence shrinks step by step until it fits, keeping what the claims cite."""

import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from judges import citation_ground_custom_judge as judge
from judges.judge_evidence import (
    MAX_LEVEL,
    build_judge_bundle,
    fit_judge_bundle,
    judge_bundle_json,
)
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
        sha = hashlib.sha1(str(i).encode()).hexdigest()
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
    lines = [f"C{i} [testing]: {bundle.repo_snapshot.files[i * 3].path}:L1-L9 | covers the module" for i in range(n // 2)]
    lines += [f"C{n // 2 + i} [cicd]: {bundle.commits[i * 5].sha[:9]} | added a step" for i in range(n // 2)]
    return "\n".join(lines)


def test_level_zero_is_the_default() -> None:
    bundle = sprint_like_your_data(n_commits=10)
    claims = many_claims(bundle, n=4)
    assert build_judge_bundle(bundle, claims, level=0) == build_judge_bundle(bundle, claims)


def test_each_level_is_no_larger_than_the_one_before() -> None:
    bundle = sprint_like_your_data()
    claims = many_claims(bundle)

    sizes = [len(judge_bundle_json(bundle, claims, level)) for level in range(MAX_LEVEL + 1)]

    assert sizes == sorted(sizes, reverse=True)
    assert sizes[-1] < sizes[0] / 3


def test_cited_records_are_kept_in_full_at_every_level_that_does_not_truncate() -> None:
    bundle = sprint_like_your_data()
    claims = many_claims(bundle)
    cited_commit, cited_file = bundle.commits[5], bundle.repo_snapshot.files[3]

    for level in range(MAX_LEVEL):
        judged = build_judge_bundle(bundle, claims, level)
        commit_entry = next(c for c in judged["commits"] if c["sha"] == cited_commit.sha)
        assert commit_entry["message"] == cited_commit.message
        assert all("diff" in f for f in commit_entry["files_changed"]), f"level {level} lost a cited commit's diff"
        file_entry = next(f for f in judged["repo_snapshot"]["files"] if f["path"] == cited_file.path)
        assert file_entry["content"] == cited_file.content, f"level {level} lost a cited file's content"


def test_uncited_commits_lose_detail_progressively() -> None:
    bundle = sprint_like_your_data(n_commits=40)
    claims = f"C1 [cicd]: {bundle.commits[0].sha[:9]} | x"
    uncited = bundle.commits[1]

    def entry(level):
        commits = build_judge_bundle(bundle, claims, level)["commits"]
        return next((c for c in commits if c["sha"].startswith(uncited.sha[:12])), None)

    assert len(entry(0)["files_changed"]) == 10                                # full file list
    assert entry(1)["files_changed"] == [] and entry(1)["files_total"] == 10   # file lists dropped
    assert set(entry(2)) == {"sha", "author", "message", "date", "lines_added", "lines_deleted"}  # shrunk
    assert entry(3) is None                                                    # replaced by totals


def test_level_three_totals_match_the_commits_that_were_dropped() -> None:
    bundle = sprint_like_your_data(n_commits=40)
    claims = f"C1 [cicd]: {bundle.commits[0].sha[:9]} | x"

    judged = build_judge_bundle(bundle, claims, 3)

    assert judged["commits_total"] == 40
    assert sum(a["commits"] for a in judged["other_commits_by_author"].values()) == 39  # all but the cited one
    assert sum(a["lines_added"] for a in judged["other_commits_by_author"].values()) == 39 * 40
    assert "note" in judged


def _commit_with_files(sha: str, n_files: int) -> CommitInfo:
    return CommitInfo(
        sha=sha, author="a", message="m", timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        files_changed=[
            FileDiff(filename=f"src/f{i}.py", lines_added=10 * (i + 1), lines_deleted=0, diff=f"diff of file {i}\n" * 5)
            for i in range(n_files)
        ],
    )


SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"


def _diff_names(judged) -> set[str]:
    return {f["filename"] for f in judged["commits"][0]["files_changed"] if "diff" in f}


def test_a_cited_commit_shows_all_its_diffs_until_the_last_level() -> None:
    bundle = ArtifactBundle(team_id="t", sprint_id="s", commits=[_commit_with_files(SHA, 5)])

    assert len(_diff_names(build_judge_bundle(bundle, f"{SHA[:9]} | x", 3))) == 5


def test_at_the_last_level_a_cited_commit_keeps_diffs_for_the_files_the_claims_mention() -> None:
    bundle = ArtifactBundle(team_id="t", sprint_id="s", commits=[_commit_with_files(SHA, 5)])

    judged = build_judge_bundle(bundle, f"{SHA[:9]} src/f1.py | changed the f1 module", MAX_LEVEL)

    assert _diff_names(judged) == {"src/f1.py"}
    assert len(judged["commits"][0]["files_changed"]) == 5  # the file list itself is still complete


def test_at_the_last_level_a_cited_commit_with_no_named_file_keeps_its_three_largest_changes() -> None:
    bundle = ArtifactBundle(team_id="t", sprint_id="s", commits=[_commit_with_files(SHA, 5)])

    judged = build_judge_bundle(bundle, f"{SHA[:9]} | a big change", MAX_LEVEL)

    assert _diff_names(judged) == {"src/f4.py", "src/f3.py", "src/f2.py"}


def test_kept_diffs_are_never_cut_off() -> None:
    commit = _commit_with_files(SHA, 1)
    commit.files_changed[0].diff = "x" * 50_000
    bundle = ArtifactBundle(team_id="t", sprint_id="s", commits=[commit])

    judged = build_judge_bundle(bundle, f"{SHA[:9]} | x", MAX_LEVEL)

    assert judged["commits"][0]["files_changed"][0]["diff"] == "x" * 50_000  # truncation would invite false 'hallucinated'


def _bundle_with_file(lines: int = 100) -> ArtifactBundle:
    content = "\n".join(f"line {i}" for i in range(1, lines + 1))
    return ArtifactBundle(
        team_id="t", sprint_id="s",
        repo_snapshot=RepoSnapshot(files=[SnapshotFile(path="src/auth.py", size_bytes=len(content), content=content)]),
    )


def test_at_the_last_level_a_cited_file_shows_only_the_cited_lines_with_context() -> None:
    judged = build_judge_bundle(_bundle_with_file(), "src/auth.py:L40-L45@abc1234 | token check", MAX_LEVEL)

    entry = judged["repo_snapshot"]["files"][0]
    assert "content" not in entry
    (excerpt,) = entry["excerpts"]
    assert (excerpt["from"], excerpt["to"]) == (30, 55)
    assert excerpt["text"].splitlines()[0] == "line 30" and excerpt["text"].splitlines()[-1] == "line 55"


def test_overlapping_and_distant_line_ranges() -> None:
    claims = "src/auth.py:L10-L20 | a\nsrc/auth.py:L25-L30 | b\nsrc/auth.py:L90 | c"

    entry = build_judge_bundle(_bundle_with_file(), claims, MAX_LEVEL)["repo_snapshot"]["files"][0]

    assert [(e["from"], e["to"]) for e in entry["excerpts"]] == [(1, 40), (80, 100)]  # near ranges merge, far one stays apart


def test_a_cited_file_with_no_line_range_keeps_its_whole_content() -> None:
    entry = build_judge_bundle(_bundle_with_file(), "src/auth.py | the module", MAX_LEVEL)["repo_snapshot"]["files"][0]

    assert entry["content"].count("\n") == 99 and "excerpts" not in entry


def test_the_note_explains_the_narrowing_only_when_it_happened() -> None:
    bundle = ArtifactBundle(team_id="t", sprint_id="s", commits=[_commit_with_files(SHA, 2)])

    assert "note" not in build_judge_bundle(bundle, f"{SHA[:9]} | x", 0)
    assert "largest changes" not in build_judge_bundle(bundle, f"{SHA[:9]} | x", 2)["note"]
    assert "largest changes" in build_judge_bundle(bundle, f"{SHA[:9]} | x", MAX_LEVEL)["note"]


def test_fit_chooses_the_least_reduced_level_that_fits() -> None:
    bundle = sprint_like_your_data()
    claims = many_claims(bundle)
    sizes = [len(judge_bundle_json(bundle, claims, level)) for level in range(MAX_LEVEL + 1)]

    for target in range(MAX_LEVEL + 1):
        _, level, _ = fit_judge_bundle(bundle, claims, max_chars=sizes[target])
        assert level <= target


def test_fit_returns_the_most_reduced_view_and_its_sizes_when_nothing_fits() -> None:
    bundle = sprint_like_your_data()

    text, level, sizes = fit_judge_bundle(bundle, many_claims(bundle), max_chars=10)

    assert level == MAX_LEVEL and len(text) > 10
    assert {"commits", "jira_tickets", "repo_snapshot"} <= set(sizes)


def test_a_sprint_shaped_like_the_failing_one_fits_the_judge() -> None:
    bundle = sprint_like_your_data()
    claims = many_claims(bundle)
    budget = int(49_152 * 0.85 * 4) - 4_000 - len(claims) - 200  # judge context less instructions and claims

    whole = len(bundle.model_dump_json()) // 4
    text, level, _ = fit_judge_bundle(bundle, claims, max_chars=budget)

    assert whole > 150_000   # the scale of the real failure (~221K tokens, then ~708K)
    assert len(text) <= budget
    assert level <= MAX_LEVEL


def test_a_sprint_that_cites_huge_diffs_is_shrunk_a_lot_but_not_forced_to_fit() -> None:
    bundle = sprint_like_your_data(diff_lines=80)  # every file of every cited commit has a big diff
    claims = many_claims(bundle)

    whole = len(judge_bundle_json(bundle, claims, 0))
    text, level, _ = fit_judge_bundle(bundle, claims, max_chars=10)

    assert level == MAX_LEVEL
    assert len(text) < whole / 3   # far smaller, yet cited evidence is not cut to make it fit


# --------------------------------------------------------------- inside the judge


def _stub_judge(monkeypatch, ctx: int = 49_152) -> dict:
    seen: dict = {}

    class Completions:
        async def create(self, **kwargs):
            seen["prompt"] = kwargs["messages"][1]["content"]
            return judge.GroundingVerdict(
                citation_verdicts=[judge.CitationVerdict(citation_id="C1", reasoning="Checked the record.",
                                                         label="grounded", severity="none")],
                judge_notes="All claims check out.",
            )

    monkeypatch.setattr(judge, "create_llm_client",
                        lambda provider="ollama": SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": ctx})
    return seen


def test_the_judge_runs_on_a_sprint_that_used_to_overflow_it(monkeypatch) -> None:
    seen = _stub_judge(monkeypatch)
    bundle = sprint_like_your_data()
    claims = {"C1": {"dimension": "testing", "text": f"{bundle.commits[3].sha[:9]} | a change"}}

    verdict = asyncio.run(judge.run_grounding_judge(bundle, claims, "judge-x"))

    assert verdict.citation_verdicts[0].label == "grounded"
    assert len(seen["prompt"]) // 4 < 49_152 * 0.85
    assert bundle.commits[3].sha in seen["prompt"]  # the cited commit is there in full


def test_an_unfittable_prompt_reports_where_the_tokens_are(monkeypatch) -> None:
    _stub_judge(monkeypatch, ctx=1_000)  # too small even for a one-citation view of a real sprint
    bundle = sprint_like_your_data()
    claims = {"C1": {"dimension": "testing", "text": f"{bundle.commits[3].sha[:9]} | a change"}}

    with pytest.raises(judge.JudgeContextTooSmall) as raised:
        asyncio.run(judge.run_grounding_judge(bundle, claims, "judge-x"))

    message = str(raised.value)
    assert "most reduced evidence view" in message and "largest sections in tokens" in message
