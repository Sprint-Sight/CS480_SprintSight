"""A claim anchored on a file but describing "the commit" can be checked: the file's key commits stay visible."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from judges.citation_ground_custom_judge import (
    GROUNDING_PROMPT_VERSION,
    GROUNDING_SYSTEM_PROMPT,
)
from judges.judge_evidence import MAX_LEVEL, build_judge_bundle, judge_bundle_json
from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff

PILL = "shuttlescore/src/app/components/userPill.js"
SERVICE = "tournament-management/src/main/java/service/impl/TournamentServiceImpl.java"
START = datetime(2026, 1, 1, tzinfo=UTC)


def sha_of(label: str) -> str:
    return hashlib.sha1(label.encode(), usedforsecurity=False).hexdigest()


def commit(label: str, files: list[str], day: int, message: str | None = None, author: str = "alice",
           change: str = "modified") -> CommitInfo:
    return CommitInfo(
        sha=sha_of(label), author=author, message=message or f"message of {label}",
        timestamp=START + timedelta(days=day), lines_added=10, lines_deleted=2,
        files_changed=[FileDiff(filename=f, change_type=change, lines_added=10, lines_deleted=2, diff="+x\n" * 20)
                       for f in files],
    )


# The claim shape from a real run: a FILE is the identifier, the explanation is about a commit.
CLAIM = f"C8 [code_quality]: {PILL} | The commit adds a user pill component, demonstrating clear commit messaging."
INTRODUCES = f"C1 [code_quality]: {SERVICE} | This commit introduces the TournamentServiceImpl class, which handles tournament creation."


def bundle(*commits: CommitInfo) -> ArtifactBundle:
    return ArtifactBundle(team_id="t", sprint_id="s", commits=list(commits))


def entries(judged: dict) -> dict[str, dict]:
    return {c["message"]: c for c in judged["commits"]}


def long_history() -> ArtifactBundle:
    """A service class created on day 1 and edited by 20 later commits, the shape of the real misjudgements."""
    created = commit("created", [SERVICE], day=1, message="create CRUD controller and service for all entities", change="added")
    later = [commit(f"fix{i}", [SERVICE], day=2 + i, message=f"fix {i}") for i in range(20)]
    return bundle(created, *later)


# ---- the real failure: the judge was shown only the newest commits -------------------------------


def test_the_commit_that_created_a_file_is_shown_for_a_claim_that_this_commit_introduces_it() -> None:
    for level in (2, 3, MAX_LEVEL):
        found = entries(build_judge_bundle(long_history(), INTRODUCES, level))
        assert "create CRUD controller and service for all entities" in found, f"level {level}: the creating commit is missing"
        assert found["create CRUD controller and service for all entities"]["adds"] == [SERVICE]


def test_a_file_shows_its_creating_commit_and_its_two_newest_and_nothing_else() -> None:
    judged = build_judge_bundle(long_history(), INTRODUCES, 3)

    assert sorted(entries(judged)) == sorted(["create CRUD controller and service for all entities", "fix 18", "fix 19"])
    assert judged["other_commits_by_author"]["alice"]["commits"] == 18  # the other 18 edits are only totalled
    assert all("adds" not in c for c in judged["commits"] if c["message"].startswith("fix"))


def test_the_newest_commits_are_still_listed_for_claims_about_recent_work() -> None:
    found = entries(build_judge_bundle(long_history(), INTRODUCES, MAX_LEVEL))
    assert {"fix 18", "fix 19"} <= set(found)
    assert found["fix 19"]["touches"] == [SERVICE]


# ---- choosing the creating commit ---------------------------------------------------------------


def test_the_commit_recorded_as_adding_the_file_wins_over_an_earlier_one_that_only_modified_it() -> None:
    touched_first = commit("first", [SERVICE], day=1, message="tweak before the move")
    added = commit("added", [SERVICE], day=2, message="add the service", change="added")
    sprint = bundle(touched_first, added, *(commit(f"m{i}", [SERVICE], day=3 + i) for i in range(5)))

    found = entries(build_judge_bundle(sprint, INTRODUCES, 3))

    assert found["add the service"]["adds"] == [SERVICE]
    assert "tweak before the move" not in found


def test_with_no_commit_recorded_as_adding_it_the_earliest_commit_is_used_without_claiming_it_created_the_file() -> None:
    sprint = bundle(*(commit(f"c{i}", [SERVICE], day=i) for i in range(6)))

    found = entries(build_judge_bundle(sprint, INTRODUCES, 3))

    assert "message of c0" in found                     # earliest touching commit
    assert "adds" not in found["message of c0"]         # but it is not asserted to have created the file
    assert {"message of c4", "message of c5"} <= set(found)


def test_a_file_created_twice_names_only_its_first_creation() -> None:
    first = commit("first", [PILL], day=1, message="created pill", change="added")
    again = commit("again", [PILL], day=9, message="re-created pill", change="added")
    sprint = bundle(first, again, commit("edit", [PILL], day=10))

    found = entries(build_judge_bundle(sprint, CLAIM, 3))

    assert found["created pill"]["adds"] == [PILL]
    assert "adds" not in found.get("re-created pill", {})


def test_a_single_commit_touching_a_file_is_listed_once() -> None:
    sprint = bundle(commit("pill", [PILL], day=5, message="Player Pill component added", change="added"))

    commits = build_judge_bundle(sprint, CLAIM, 3)["commits"]

    assert [c["message"] for c in commits] == ["Player Pill component added"]
    assert commits[0]["adds"] == [PILL] and commits[0]["touches"] == [PILL]


# ---- the rest of the behaviour -------------------------------------------------------------------


def test_unrelated_commits_are_still_only_totals_at_level_three() -> None:
    sprint = bundle(commit("pill", [PILL], day=5), commit("other", ["README.md"], day=6), commit("other2", ["x.py"], day=7))

    judged = build_judge_bundle(sprint, CLAIM, 3)

    assert [c["message"] for c in judged["commits"]] == ["message of pill"]
    assert judged["other_commits_by_author"]["alice"]["commits"] == 2
    assert judged["commits_total"] == 3


def test_a_commit_touching_two_cited_files_lists_both_and_marks_only_what_it_created() -> None:
    other = "tournament-management/src/Elo.java"
    sprint = bundle(commit("both", [PILL, other], day=1, change="added"), commit("later", [PILL], day=2))
    claims = f"{CLAIM}\nC9 [code_quality]: {other} | Elo logic."

    found = entries(build_judge_bundle(sprint, claims, 3))

    assert sorted(found["message of both"]["touches"]) == sorted([PILL, other])
    assert sorted(found["message of both"]["adds"]) == sorted([PILL, other])
    assert "adds" not in found["message of later"]


def test_levels_below_two_are_unchanged() -> None:
    sprint = bundle(commit("pill", [PILL], day=5), commit("other", ["README.md"], day=6))

    for level in (0, 1):
        assert all("touches" not in c and "adds" not in c for c in build_judge_bundle(sprint, CLAIM, level)["commits"])


def test_at_level_two_the_key_commits_are_marked_and_the_rest_are_short_entries() -> None:
    sprint = bundle(commit("pill", [PILL], day=5), commit("other", ["README.md"], day=6))

    found = entries(build_judge_bundle(sprint, CLAIM, 2))

    assert found["message of pill"]["touches"] == [PILL]
    assert "touches" not in found["message of other"]


def test_a_key_commits_message_is_not_cut_as_short_as_an_ordinary_one() -> None:
    long_message = "x" * 250
    sprint = bundle(commit("pill", [PILL], day=1, message=long_message), commit("other", ["a.py"], day=2, message=long_message))

    at_two = {c["sha"]: c for c in build_judge_bundle(sprint, CLAIM, 2)["commits"]}

    assert at_two[sha_of("pill")[:12]]["message"] == long_message
    assert at_two[sha_of("other")[:12]]["message"] == "x" * 100 + "..."


def test_a_commit_cited_by_sha_is_not_listed_twice() -> None:
    cited = commit("pill", [PILL], day=1)
    sprint = bundle(cited, commit("other", ["a.py"], day=2))
    claims = f"{CLAIM}\nC9 [testing]: {cited.sha[:9]} | the same commit"

    commits = build_judge_bundle(sprint, claims, 3)["commits"]

    assert [c["sha"] for c in commits] == [cited.sha]
    assert "touches" not in commits[0]


def test_a_cited_file_no_commit_touched_adds_nothing() -> None:
    sprint = bundle(commit("other", ["a.py"], day=1))

    judged = build_judge_bundle(sprint, CLAIM, 3)

    assert judged["commits"] == [] and judged["commits_total"] == 1
    assert "created it" not in judged["note"]


def test_the_note_says_these_are_only_some_of_the_files_commits() -> None:
    note = build_judge_bundle(bundle(commit("pill", [PILL], day=1)), CLAIM, 3)["note"]

    assert "created it" in note and "only some of the file's commits" in note


def test_the_extra_commits_cost_little_next_to_what_they_replace() -> None:
    sprint = bundle(*(commit(f"c{i}", [f"src/f{i % 30}.py"], day=i % 60) for i in range(311)))
    claims = "\n".join(f"C{i} [testing]: src/f{i}.py | covers the module" for i in range(30))

    with_history = len(judge_bundle_json(sprint, claims, 3))
    without = len(json.dumps(build_judge_bundle(bundle(), claims, 3)))

    assert with_history - without < 30 * 3 * 700  # three short entries per cited file, at most


# ---- the prompt ----------------------------------------------------------------------------------


def test_the_prompt_version_records_that_the_judge_input_and_rules_changed() -> None:
    assert GROUNDING_PROMPT_VERSION == "grounding-v5"


def test_the_prompt_tells_the_judge_not_to_call_an_unverifiable_file_claim_fabricated() -> None:
    assert "Do not label such a claim hallucinated just because the newest" in GROUNDING_SYSTEM_PROMPT
    assert "partially_grounded with severity minor_detail" in GROUNDING_SYSTEM_PROMPT
    assert "Use hallucinated only when a listed" in GROUNDING_SYSTEM_PROMPT
    assert 'citation_id is only the id' in GROUNDING_SYSTEM_PROMPT
