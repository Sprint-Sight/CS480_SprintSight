"""The judge canary must import, build real claims, and fail loudly on a bad judge."""

import random
from types import SimpleNamespace

from evaluation.benchmarks.cs203 import CS203G6_GOLD
from evaluation.offline import judge_canary
from evaluation.offline.judge_canary import build_canary_claims, main, mutate


def test_the_canary_module_imports() -> None:
    # It once imported schemas.cs203_groundtruth, which never existed (the module is evaluation.benchmarks.cs203).
    assert callable(judge_canary.main)


def test_the_gold_yields_true_claims_and_strictly_different_false_ones() -> None:
    true_claims, false_claims = build_canary_claims(CS203G6_GOLD.rubric_scores, random.Random(0))

    assert len(true_claims) > 0
    assert false_claims and set(false_claims) <= set(true_claims)
    for cid, claim in false_claims.items():
        assert claim["text"] != true_claims[cid]["text"]
        assert claim["dimension"] == true_claims[cid]["dimension"]


def test_a_number_is_bumped_before_anything_else() -> None:
    assert mutate("added +105 lines in a1b2c3d") == "added +950 lines in a1b2c3d"


def test_a_claim_with_a_sha_and_no_digits_gets_a_new_sha() -> None:
    sha = "abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    mutated = mutate(f"commit {sha} by alice", random.Random(1))
    assert mutated != f"commit {sha} by alice" and mutated.startswith("commit ")


def test_a_claim_that_cannot_be_falsified_is_left_unchanged() -> None:
    assert mutate("clear commit message") == "clear commit message"


def _fake_judge(monkeypatch, *, always: str | None = None):
    """A judge that is right (grounded iff the claim is unmutated) or always says `always`."""
    true_claims, _ = build_canary_claims(CS203G6_GOLD.rubric_scores)
    originals = {cid: claim["text"] for cid, claim in true_claims.items()}

    async def judge(bundle, claims, model, provider="ollama"):
        verdicts = []
        for cid, claim in claims.items():
            label = always or ("grounded" if claim["text"] == originals[cid] else "hallucinated")
            verdicts.append(SimpleNamespace(citation_id=cid, label=label))
        return SimpleNamespace(citation_verdicts=verdicts)

    monkeypatch.setattr(judge_canary, "run_grounding_judge", judge)


def test_a_correct_judge_passes(monkeypatch, capsys) -> None:
    _fake_judge(monkeypatch)
    assert main(["any-model", "--repeats", "2"]) == 0
    assert "canary ok" in capsys.readouterr().out


def test_a_judge_that_rubber_stamps_everything_fails(monkeypatch, capsys) -> None:
    _fake_judge(monkeypatch, always="grounded")
    assert main(["any-model", "--repeats", "1"]) == 1
    assert "mutated" in capsys.readouterr().out.split("CANARY FAILED")[1]


def test_a_judge_that_rejects_everything_fails(monkeypatch) -> None:
    _fake_judge(monkeypatch, always="hallucinated")
    assert main(["any-model", "--repeats", "1"]) == 1
