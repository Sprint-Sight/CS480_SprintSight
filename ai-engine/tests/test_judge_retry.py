"""A dropped connection to the judge model is retried per call, so one blip does not fail the judge."""

import asyncio

import httpx
import openai
import pytest

from evaluation.judges import citation_grounding as cg


def _dropped_connection() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "http://judge.invalid"))


def test_a_dropped_connection_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _dropped_connection()
        return "ok"

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(cg, "_judge_batch", flaky)
    monkeypatch.setattr(cg.asyncio, "sleep", no_sleep)

    assert asyncio.run(cg._judge_batch_retrying()) == "ok"
    assert calls["n"] == 3  # failed twice, succeeded on the third attempt


def test_a_persistent_failure_is_raised_after_the_last_attempt(monkeypatch):
    calls = {"n": 0}

    async def always_down(*args, **kwargs):
        calls["n"] += 1
        raise _dropped_connection()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(cg, "_judge_batch", always_down)
    monkeypatch.setattr(cg.asyncio, "sleep", no_sleep)

    with pytest.raises(openai.APIConnectionError):
        asyncio.run(cg._judge_batch_retrying())
    assert calls["n"] == 3  # gives up after 3 attempts, never loops forever


def test_a_non_transient_failure_is_not_retried(monkeypatch):
    calls = {"n": 0}

    async def bad_prompt(*args, **kwargs):
        calls["n"] += 1
        raise cg.JudgeContextTooSmall("the prompt cannot fit")

    monkeypatch.setattr(cg, "_judge_batch", bad_prompt)

    with pytest.raises(cg.JudgeContextTooSmall):
        asyncio.run(cg._judge_batch_retrying())
    assert calls["n"] == 1  # retrying a prompt that cannot fit would never help
