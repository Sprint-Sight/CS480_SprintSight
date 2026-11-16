"""The judge canary must import, falsify only the reason of a claim, and fail loudly on a bad judge."""

import random
from types import SimpleNamespace

import pytest

from evaluation.offline import judge_canary
from evaluation.offline.judge_canary import (
    CANARY_TEAMS,
    build_canary_claims,
    bundle_authors,
    main,
    mutate,
)

AUTHORS = ["student1", "student2", "student3"]


def _identifier(text: str) -> str:
    return text.partition(" | ")[0]


def _claims(rng_seed: int = 0):
    return {
        team: (bundle, *build_canary_claims(gold.rubric_scores, random.Random(rng_seed), authors=bundle_authors(bundle)))
        for team, bundle, gold in CANARY_TEAMS
    }


def test_the_canary_module_imports() -> None:
    # It once imported schemas.cs203_groundtruth, which never existed (the module is evaluation.benchmarks.cs203).
    assert callable(judge_canary.main)


def test_both_benchmark_teams_are_in_the_canary() -> None:
    assert [team for team, _, _ in CANARY_TEAMS] == ["cs203g6", "cs203jy"]


@pytest.mark.parametrize("seed", range(5))
def test_the_gold_yields_false_claims_whose_identifier_is_untouched(seed: int) -> None:
    for team, (_, true_claims, false_claims) in _claims(seed).items():
        assert len(true_claims) > 0, team
        assert false_claims and set(false_claims) <= set(true_claims), team
        for cid, claim in false_claims.items():
            original = true_claims[cid]
            assert claim["text"] != original["text"], (team, cid)
            assert _identifier(claim["text"]) == _identifier(original["text"]), (team, cid)  # the whole point
            assert claim["dimension"] == original["dimension"]


def test_a_number_in_the_reason_is_bumped_and_the_identifier_is_not() -> None:
    sha = "7373c90c578ff7614f8c0a3ecac58a4ccba1cd4b"
    mutated = mutate(f"{sha} | 'refactor' is the clearest commit (+105 lines).", random.Random(0))
    assert mutated == f"{sha} | 'refactor' is the clearest commit (+950 lines)."


def test_a_digit_inside_the_identifier_is_never_the_one_changed() -> None:
    # The old canary bumped the first number it found: here the 7 of the SHA, producing a SHA the
    # engine would have dropped before the judge ever saw it.
    claim = "7373c90c | adds 12 lines"
    for seed in range(10):
        assert mutate(claim, random.Random(seed)).startswith("7373c90c | adds ")
    assert mutate(claim, random.Random(0)) == "7373c90c | adds 857 lines"


def test_grouped_numbers_stay_grouped() -> None:
    assert mutate("abc | deletes 1,184 lines", random.Random(0)) == "abc | deletes 2,029 lines"


@pytest.mark.parametrize("reason", [
    "short SHA 37f65c3 is cited",            # digits inside a hex word
    "ticket CG-46 was closed",               # key
    "see CS203-10",                           # key with letters+digits
    "Merge pull request #16",                 # PR number
    "student2 wrote the tests",               # handle
    "Junhao186 and Leman-24-horas",           # handles with digits
    "scores 3.5 out of ten",                  # decimal, not a standalone integer
])
def test_numbers_that_are_part_of_a_name_or_key_are_not_mutated(reason: str) -> None:
    assert mutate(f"id | {reason}", random.Random(0)) == f"id | {reason}"


def test_a_number_outside_a_quoted_commit_message_is_preferred() -> None:
    assert mutate("id | 'deploy 11' adds 31 lines", random.Random(0)) == "id | 'deploy 11' adds 876 lines"


def test_an_author_is_swapped_for_another_author_of_the_bundle() -> None:
    mutated = mutate("id | explicit test commit by student2 (no numbers)", random.Random(0), AUTHORS)
    assert mutated == "id | explicit test commit by student1 (no numbers)"
    assert "student2" not in mutated


def test_a_claim_with_a_number_and_an_author_gets_exactly_one_change_either_way() -> None:
    original = "id | student2 authored 95 commits"
    seen = {mutate(original, random.Random(seed), AUTHORS) for seed in range(20)}
    assert seen == {"id | student1 authored 95 commits", "id | student2 authored 940 commits"}


def test_a_claim_that_cannot_be_falsified_is_left_unchanged() -> None:
    assert mutate("abc | clear commit message") == "abc | clear commit message"
    assert mutate("clear commit message with 12 lines") == "clear commit message with 12 lines"  # no identifier split


def test_the_authors_come_from_the_commits_of_each_bundle() -> None:
    by_team = {team: bundle_authors(bundle) for team, bundle, _ in CANARY_TEAMS}
    assert by_team["cs203g6"] == ["Student1", "Student2", "Student3"]
    assert "student5" in by_team["cs203jy"] and len(by_team["cs203jy"]) == 5


def _fake_judge(monkeypatch, *, always: str | None = None):
    """A judge that is right (grounded iff the claim is unmutated) or always says `always`."""
    originals = {
        bundle.team_id: {cid: claim["text"] for cid, claim in build_canary_claims(gold.rubric_scores)[0].items()}
        for _, bundle, gold in CANARY_TEAMS
    }

    async def judge(bundle, claims, model, provider="ollama"):
        verdicts = []
        for cid, claim in claims.items():
            label = always or ("grounded" if claim["text"] == originals[bundle.team_id][cid] else "hallucinated")
            verdicts.append(SimpleNamespace(citation_id=cid, label=label))
        return SimpleNamespace(citation_verdicts=verdicts)

    monkeypatch.setattr(judge_canary, "run_grounding_judge", judge)


def test_a_correct_judge_passes(monkeypatch, capsys) -> None:
    _fake_judge(monkeypatch)
    assert main(["any-model", "--repeats", "2"]) == 0
    out = capsys.readouterr().out
    assert "canary ok" in out
    assert "cs203g6 mutated" in out and "cs203jy mutated" in out


def test_a_judge_that_rubber_stamps_everything_fails(monkeypatch, capsys) -> None:
    _fake_judge(monkeypatch, always="grounded")
    assert main(["any-model", "--repeats", "1"]) == 1
    assert "mutated" in capsys.readouterr().out.split("CANARY FAILED")[1]


def test_a_judge_that_rejects_everything_fails(monkeypatch) -> None:
    _fake_judge(monkeypatch, always="hallucinated")
    assert main(["any-model", "--repeats", "1"]) == 1
