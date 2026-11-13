"""The judge model sometimes copies the whole claim line into citation_id; that must not sink the verdicts."""

import asyncio
from types import SimpleNamespace

import pytest

from evaluation.judges import citation_grounding as judge
from evaluation.judges.citation_grounding import (
    _PREVIEW_CHARS,
    CitationVerdict,
    make_grounding_verdict_model,
)
from schemas.artifact_bundle import ArtifactBundle
from services.failures import failure_detail

# Taken from a real run: the model wrote the claim as shown to it into the id field, four times in a row.
WHOLE_LINE = "C4 [code_quality]: 5e1526c | Clear commit message for completing a major feature (authorization/authentication)."


def verdict(citation_id: str) -> dict:
    return {"citation_id": citation_id, "reasoning": "The record says so.", "label": "grounded", "severity": "none"}


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        (WHOLE_LINE, "C4"),
        ("C4", "C4"),
        ("c4", "C4"),
        (" C12: some text", "C12"),
        ("C7 [testing]: tournament-management/src/test/X.java:L1-L150 | Test file includes setup.", "C7"),
    ],
)
def test_the_id_is_the_leading_claim_label(written, expected) -> None:
    assert CitationVerdict(**verdict(written)).citation_id == expected


def test_something_that_is_not_a_claim_label_is_left_alone_to_fail_validation() -> None:
    assert CitationVerdict(**verdict("not an id")).citation_id == "not an id"
    assert CitationVerdict(**verdict("C")).citation_id == "C"          # no digits
    assert CitationVerdict(**verdict("C4x")).citation_id == "C4x"      # not a clean label


def test_the_answer_that_failed_four_times_in_a_row_now_validates() -> None:
    model = make_grounding_verdict_model({"C4", "C5", "C6", "C7"})
    lines = [WHOLE_LINE.replace("C4", f"C{n}") for n in (4, 5, 6, 7)]

    result = model.model_validate({"citation_verdicts": [verdict(line) for line in lines], "judge_notes": "Checked all four."})

    assert [v.citation_id for v in result.citation_verdicts] == ["C4", "C5", "C6", "C7"]


def test_a_missing_unknown_or_repeated_claim_is_still_rejected() -> None:
    model = make_grounding_verdict_model({"C4", "C5"})
    notes = "Checked the claims."

    with pytest.raises(ValueError, match="Missing"):
        model.model_validate({"citation_verdicts": [verdict(WHOLE_LINE)], "judge_notes": notes})
    with pytest.raises(ValueError, match="unknown"):
        model.model_validate({"citation_verdicts": [verdict("C4"), verdict("C5"), verdict("C99 [x]: y")], "judge_notes": notes})
    with pytest.raises(ValueError, match="duplicated"):
        model.model_validate({"citation_verdicts": [verdict("C4"), verdict(WHOLE_LINE), verdict("C5")], "judge_notes": notes})


def test_the_judge_accepts_whole_line_ids_end_to_end(monkeypatch) -> None:
    calls = []

    class Completions:
        async def create(self, **kwargs):
            calls.append(1)
            model = kwargs["response_model"]
            prompt = kwargs["messages"][1]["content"]
            lines = [line for line in prompt.split("CLAIMS TO CHECK:\n")[1].splitlines() if line.strip()]
            return model.model_validate({"citation_verdicts": [verdict(line) for line in lines], "judge_notes": "Checked every claim."})

    monkeypatch.setattr(judge, "create_llm_client",
                        lambda provider="ollama": SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": 16_384})
    claims = {f"C{i}": {"dimension": "testing", "text": f"src/f{i}.py | covers the module"} for i in range(1, 6)}

    result = asyncio.run(judge.run_grounding_judge(ArtifactBundle(team_id="t", sprint_id="s"), claims, "judge-x"))

    assert [v.citation_id for v in result.citation_verdicts] == list(claims)
    assert len(calls) == 1  # no retries needed


def test_a_long_judge_error_fits_mlflows_preview_column() -> None:
    # An instructor error carrying every failed attempt was ~25,000 characters; the trace table's
    # preview column holds 1000, and the rejected insert dropped the whole judge trace.
    huge = RuntimeError("<failed_attempts>" + "x" * 25_000)

    preview = f"Error: {failure_detail(huge, 500)}"

    assert len(preview) < 1000 and _PREVIEW_CHARS < 1000
