"""The judge works inside the window the model really has, in as many calls as that takes."""

import asyncio
import logging
import re
from types import SimpleNamespace

import pytest
from test_judge_evidence_ladder import sprint_like_your_data

from judges import citation_ground_custom_judge as judge
from judges.citation_ground_custom_judge import (
    GROUNDING_SYSTEM_PROMPT,
    HOSTED_JUDGE_CONTEXT,
    JUDGE_CALL_DEADLINE_SECONDS,
    JUDGE_SCORER_TIMEOUT_SECONDS,
    JudgeContextTooSmall,
    _budget_chars,
    _judge_context,
    plan_batches,
)
from judges.citation_ground_custom_judge import (
    _server_context_limit as real_server_context_limit,
)

PHI_WINDOW = 16_384  # what phi4:14b really has


def realistic_claims(bundle, n: int = 90) -> dict:
    """~90 citations spread over files and commits: six dimensions with the maximum 15 each."""
    claims = {}
    for i in range(n):
        if i % 2:
            text = f"{bundle.commits[(i * 3) % len(bundle.commits)].sha[:9]} | added a step to the pipeline"
        else:
            text = f"{bundle.repo_snapshot.files[(i * 2) % len(bundle.repo_snapshot.files)].path}:L1-L9 | covers the module"
        claims[f"C{i + 1}"] = {"dimension": ("testing", "cicd", "documentation")[i % 3], "text": text}
    return claims


# ------------------------------------------------------------------ planning the calls


def test_the_window_reserves_room_for_the_verdicts_it_must_write() -> None:
    few = _budget_chars(PHI_WINDOW, 2, 500)
    many = _budget_chars(PHI_WINDOW, 40, 500)

    assert few - many == 38 * judge._OUTPUT_TOKENS_PER_CLAIM * 4


def test_a_small_sprint_is_judged_in_one_call() -> None:
    bundle = sprint_like_your_data(n_commits=20, n_files=10)
    claims = realistic_claims(bundle, n=6)

    batches = plan_batches(bundle, claims, PHI_WINDOW)

    assert len(batches) == 1 and batches[0].ids == list(claims)


def test_a_real_sized_sprint_is_split_so_every_call_fits_the_16k_window() -> None:
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    batches = plan_batches(bundle, claims, PHI_WINDOW)

    assert len(batches) > 1
    for batch in batches:
        prompt_tokens = (len(GROUNDING_SYSTEM_PROMPT) + len(batch.bundle_json) + len(batch.claims_text)) // 4
        output_tokens = judge._OUTPUT_FIXED_TOKENS + judge._OUTPUT_TOKENS_PER_CLAIM * len(batch.ids)
        assert prompt_tokens + output_tokens <= PHI_WINDOW * 0.85, f"{len(batch.ids)} claims: {prompt_tokens}+{output_tokens}"


def test_every_claim_is_judged_exactly_once_and_in_order() -> None:
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    batches = plan_batches(bundle, claims, PHI_WINDOW)

    assert [cid for batch in batches for cid in batch.ids] == list(claims)


def test_each_call_holds_the_evidence_for_its_own_claims() -> None:
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    for batch in plan_batches(bundle, claims, PHI_WINDOW):
        for cid in batch.ids:
            sha = re.match(r"([0-9a-f]{9}) \|", claims[cid]["text"])
            if sha:
                full = next(c.sha for c in bundle.commits if c.sha.startswith(sha.group(1)))
                assert full in batch.bundle_json, f"{cid}'s commit is missing from its own call"


def test_a_bigger_window_needs_fewer_calls() -> None:
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    assert len(plan_batches(bundle, claims, 49_152)) < len(plan_batches(bundle, claims, PHI_WINDOW))


def test_a_claim_that_cannot_fit_even_alone_fails_naming_it() -> None:
    bundle = sprint_like_your_data()
    claims = {"C7": {"dimension": "testing", "text": f"{bundle.commits[3].sha[:9]} | a change"}}

    with pytest.raises(JudgeContextTooSmall) as raised:
        plan_batches(bundle, claims, 1_000)

    message = str(raised.value)
    assert "C7" in message and "most reduced evidence view" in message and "largest sections in tokens" in message


# ------------------------------------------------------------------ running the calls


def _fake_llm(monkeypatch, calls: list):
    class Completions:
        async def create(self, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            ids = re.findall(r"^(C\d+) \[", prompt, re.MULTILINE)
            calls.append(ids)
            return judge.GroundingVerdict(
                citation_verdicts=[judge.CitationVerdict(citation_id=i, reasoning="Checked the record.",
                                                         label="grounded", severity="none") for i in ids],
                judge_notes=f"Checked {len(ids)} claims.",
            )

    monkeypatch.setattr(judge, "create_llm_client",
                        lambda provider="ollama": SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": PHI_WINDOW})


def test_verdicts_from_every_call_come_back_as_one_complete_verdict(monkeypatch) -> None:
    calls: list = []
    _fake_llm(monkeypatch, calls)
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    verdict = asyncio.run(judge.run_grounding_judge(bundle, claims, "judge-x"))

    assert len(calls) > 1
    assert [v.citation_id for v in verdict.citation_verdicts] == list(claims)  # none missing, none repeated
    assert sum(len(c) for c in calls) == len(claims)
    assert verdict.judge_notes.count("Checked") == len(calls)


def test_the_batched_verdict_scores_like_a_single_one(monkeypatch) -> None:
    _fake_llm(monkeypatch, [])
    bundle = sprint_like_your_data()
    claims = realistic_claims(bundle)

    verdict = asyncio.run(judge.run_grounding_judge(bundle, claims, "judge-x"))
    summary = judge.summarize_verdict(claims, verdict)

    assert summary["coverage"] == 1.0 and summary["grounded_rate"] == 1.0 and summary["severity_weighted_rate"] == 0.0


# --------------------------------------------- the window the server really gives


def _fake_ollama(monkeypatch, payload=None, error=None):
    class Http:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            if error:
                raise error
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(judge.httpx, "AsyncClient", Http)


PHI_INFO = {
    "model_info": {"phi3.context_length": 16384, "phi3.rope.scaling.original_context_length": 16384},
    "parameters": "num_ctx                        49152\nstop                           \"<|im_end|>\"\ntemperature                    0.1",
}


def test_the_server_limit_is_the_smaller_of_the_modelfile_and_the_trained_maximum(monkeypatch) -> None:
    _fake_ollama(monkeypatch, PHI_INFO)
    assert asyncio.run(real_server_context_limit("phi-a")) == 16_384  # asked for 49152, trained for 16384


def test_a_modelfile_smaller_than_the_trained_maximum_wins(monkeypatch) -> None:
    info = {"model_info": {"llama.context_length": 131_072}, "parameters": "num_ctx 8192"}
    _fake_ollama(monkeypatch, info)
    assert asyncio.run(real_server_context_limit("llama-a")) == 8_192


def test_an_unreachable_server_gives_no_answer_and_is_asked_again_next_time(monkeypatch) -> None:
    _fake_ollama(monkeypatch, error=ConnectionError("tunnel down"))
    assert asyncio.run(real_server_context_limit("phi-b")) is None
    assert "phi-b" not in judge._server_context

    _fake_ollama(monkeypatch, PHI_INFO)
    assert asyncio.run(real_server_context_limit("phi-b")) == 16_384


def test_a_good_answer_is_remembered(monkeypatch) -> None:
    _fake_ollama(monkeypatch, PHI_INFO)
    assert asyncio.run(real_server_context_limit("phi-c")) == 16_384

    _fake_ollama(monkeypatch, error=ConnectionError("gone"))  # would fail if it asked again
    assert asyncio.run(real_server_context_limit("phi-c")) == 16_384


def test_the_judge_uses_the_servers_smaller_window_and_says_so(monkeypatch, caplog) -> None:
    async def server_says(model):
        return 16_384

    monkeypatch.setattr(judge, "_server_context_limit", server_says)
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": 49_152})

    with caplog.at_level(logging.WARNING, logger=judge.__name__):
        assert asyncio.run(_judge_context("judge-x", "ollama")) == 16_384

    assert "49152" in caplog.text and "16384" in caplog.text


def test_the_configured_window_is_used_when_the_server_cannot_be_asked(monkeypatch) -> None:
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": 20_000})
    assert asyncio.run(_judge_context("judge-x", "ollama")) == 20_000


def test_a_server_window_larger_than_configured_does_not_raise_it(monkeypatch) -> None:
    async def server_says(model):
        return 131_072

    monkeypatch.setattr(judge, "_server_context_limit", server_says)
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": 20_000})

    assert asyncio.run(_judge_context("judge-x", "ollama")) == 20_000


def test_the_hosted_judge_has_its_own_window() -> None:
    assert asyncio.run(_judge_context("gpt-4o-mini", "openai")) == HOSTED_JUDGE_CONTEXT


def test_an_unlisted_ollama_judge_is_refused() -> None:
    with pytest.raises(ValueError, match="MODEL_NUM_CTX"):
        asyncio.run(_judge_context("not-listed", "ollama"))


def test_the_phi_judge_is_configured_for_its_real_window() -> None:
    from schemas.modelname import MODEL_NUM_CTX

    assert MODEL_NUM_CTX["sprintsight-judge-phi"] == 16_384


# ------------------------------------------------------------------ timeouts


def test_the_scorer_limit_is_far_above_mlflows_300_second_default() -> None:
    assert JUDGE_SCORER_TIMEOUT_SECONDS >= 1_800


def test_our_own_deadline_comes_before_the_scorers_so_ollama_is_stopped_cleanly() -> None:
    assert JUDGE_CALL_DEADLINE_SECONDS < JUDGE_SCORER_TIMEOUT_SECONDS
