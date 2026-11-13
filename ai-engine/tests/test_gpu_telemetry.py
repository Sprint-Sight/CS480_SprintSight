import asyncio
import importlib
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from instructor.core import IncompleteOutputException
from schemas.artifact_bundle import ArtifactBundle
from schemas.modelname import ModelName
from services import audit_logger, evaluator, llm_client

# ── services/llm_client.py ───────────────────────────────────────────────────

def test_parse_loaded_models_reports_offload_ratio():
    loaded = llm_client.parse_loaded_models(
        {"models": [{"name": "sprintsight-qwen:latest", "size": 8_000, "size_vram": 6_000, "context_length": 32000}]}
    )
    assert loaded == [{
        "name": "sprintsight-qwen:latest", "size": 8_000, "size_vram": 6_000,
        "context_length": 32000, "offload_ratio": 0.75,
    }]
    # The app names models without a tag; Ollama reports them with ":latest".
    assert llm_client.find_loaded_model(loaded, "sprintsight-qwen") is loaded[0]
    assert llm_client.find_loaded_model(loaded, "sprintsight-mistral") is None
    # evaluate_sprint receives the ModelName enum, whose str() is "ModelName.SPRINTSIGHT_QWEN".
    assert llm_client.find_loaded_model(loaded, ModelName.SPRINTSIGHT_QWEN) is loaded[0]
    assert llm_client.parse_loaded_models({}) == []


def test_request_marker_carries_run_context_and_usage():
    context = {
        "request_id": "abc", "team_id": "t1", "sprint_id": "s1", "dimension": "testing",
        "model": "sprintsight-qwen", "num_ctx": 32000, "request_started_utc": "2026-11-02T06:00:00+00:00",
    }
    body = json.dumps({"usage": {"prompt_tokens": 12000, "completion_tokens": 900}})
    with llm_client.run_context(run_id="mlflow-run", concurrency=4):
        marker = llm_client._request_marker(context, body, 200, 1234.5, "2026-11-02T06:00:05+00:00")
    assert marker["run_id"] == "mlflow-run"
    assert marker["concurrency"] == 4
    assert marker["started_at"] == "2026-11-02T06:00:00+00:00"
    assert marker["finished_at"] == "2026-11-02T06:00:05+00:00"
    assert (marker["prompt_tokens"], marker["completion_tokens"]) == (12000, 900)
    # Outside the context manager the run tags are gone again.
    assert "run_id" not in llm_client._request_marker(context, "not json", 500, 1.0, "x")


def test_write_request_marker_appends_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "markers" / "request_markers.jsonl"
    monkeypatch.setattr(audit_logger, "REQUEST_MARKERS_PATH", path)
    audit_logger.write_request_marker({"request_id": "a"})
    audit_logger.write_request_marker({"request_id": "b"})
    assert [json.loads(line)["request_id"] for line in path.read_text().splitlines()] == ["a", "b"]


def _chat_request() -> httpx.Request:
    return httpx.Request("POST", "http://ollama/v1/chat/completions", content=b'{"messages": []}')


def test_request_with_no_response_is_recorded_when_retried(tmp_path, monkeypatch, caplog):
    path = tmp_path / "request_markers.jsonl"
    monkeypatch.setattr(audit_logger, "REQUEST_MARKERS_PATH", path)
    token = llm_client._audit_context.set({"request_id": "r1", "dimension": "documentation", "model": "m"})
    try:
        asyncio.run(llm_client._capture_request(_chat_request()))   # times out, no response hook
        with caplog.at_level(logging.ERROR, logger="services.llm_client"):
            asyncio.run(llm_client._capture_request(_chat_request()))  # the client's retry
        llm_client._record_unanswered(llm_client._audit_context.get() or {})  # retry still pending
    finally:
        llm_client._audit_context.reset(token)

    markers = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(m["http_status"], m["error"]) for m in markers] == [(0, "no response"), (0, "no response")]
    assert markers[0]["started_at"] and markers[0]["finished_at"]
    assert "no response from Ollama" in caplog.text


def test_answered_request_writes_no_unanswered_marker(tmp_path, monkeypatch):
    path = tmp_path / "request_markers.jsonl"
    monkeypatch.setattr(audit_logger, "REQUEST_MARKERS_PATH", path)
    monkeypatch.setattr(llm_client, "write_audit_record", lambda record: None)
    body = json.dumps({
        "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 8192},
    }).encode()
    token = llm_client._audit_context.set({"request_id": "r1", "dimension": "testing", "model": "m"})
    try:
        request = _chat_request()
        asyncio.run(llm_client._capture_request(request))
        asyncio.run(llm_client._capture_response(httpx.Response(200, content=body, request=request)))
        llm_client._record_unanswered(llm_client._audit_context.get() or {})
    finally:
        llm_client._audit_context.reset(token)

    [marker] = [json.loads(line) for line in path.read_text().splitlines()]
    assert marker["http_status"] == 200
    assert marker["finish_reason"] == "length"   # stopped by LLM_MAX_OUTPUT_TOKENS


class _FakeCompletions:
    """chat.completions stand-in: raises IncompleteOutputException for the
    first `capped` calls, then answers; records every prompt it was sent."""

    def __init__(self, capped: int):
        self.capped = capped
        self.prompts: list[str] = []

    async def create(self, messages, **kwargs):
        self.prompts.append(messages[-1]["content"])
        if len(self.prompts) <= self.capped:
            raise IncompleteOutputException(last_completion=None)
        return {"answer": len(self.prompts), "max_tokens": kwargs["max_tokens"]}


def _fake_client(capped: int) -> SimpleNamespace:
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(capped)))


def test_normal_answer_is_sent_once_and_unchanged():
    client = _fake_client(capped=0)
    result = asyncio.run(llm_client._create_with_length_reask(client, "grade this", max_tokens=8192))
    assert result == {"answer": 1, "max_tokens": 8192}
    assert client.chat.completions.prompts == ["grade this"]


def test_capped_answer_is_re_asked_with_a_concise_note(monkeypatch):
    monkeypatch.setattr(llm_client, "_LENGTH_REASKS", 1)
    client = _fake_client(capped=1)
    result = asyncio.run(llm_client._create_with_length_reask(client, "grade this", max_tokens=8192))
    assert result["answer"] == 2
    first, second = client.chat.completions.prompts
    assert first == "grade this"
    assert second == "grade this" + llm_client._LENGTH_REASK_NOTE


def test_capped_every_time_still_fails_the_dimension(monkeypatch):
    monkeypatch.setattr(llm_client, "_LENGTH_REASKS", 1)
    client = _fake_client(capped=5)
    with pytest.raises(IncompleteOutputException):
        asyncio.run(llm_client._create_with_length_reask(client, "grade this", max_tokens=8192))
    assert len(client.chat.completions.prompts) == 2


def test_prompt_truncation_is_detected_two_ways():
    def usage(prompt_tokens: int) -> str:
        return json.dumps({"usage": {"prompt_tokens": prompt_tokens}})

    sent = {"dimension": "code_quality", "num_ctx": 32768, "estimated_prompt_tokens": 30000}
    assert llm_client._prompt_truncated(usage(16387), sent) is True    # mistral: shrank to half
    assert llm_client._prompt_truncated(usage(32500), sent) is True    # filled the context
    assert llm_client._prompt_truncated(usage(27400), sent) is False   # denser/lighter tokenizer
    assert llm_client._prompt_truncated(usage(31000), sent) is False   # retry resends more
    assert llm_client._prompt_truncated("not json", sent) is False


def test_prompt_budget_only_shrinks_models_whose_context_would_overflow():
    cap = llm_client._CONTEXT_CAP
    # Room to spare: budgets (and so prompts) unchanged.
    for model in ("sprintsight-qwen", "sprintsight-llama31", "sprintsight-gemma", ModelName.SPRINTSIGHT_QWEN):
        assert llm_client._prompt_context(model, None) == cap
    # Dense tokenizer or small context: the budget, in real tokens, fits the context.
    for model in ("sprintsight-mistral", "sprintsight-qwen25-32b", "sprintsight-r1-32b"):
        budget = llm_client._prompt_context(model, None)
        real_tokens = budget * llm_client.CHARS_PER_TOKEN / llm_client.MODEL_CHARS_PER_TOKEN[model]
        assert budget < cap
        assert real_tokens <= llm_client.MODEL_NUM_CTX[model]


# ── services/evaluator.py ────────────────────────────────────────────────────

def test_bounded_evaluate_caps_concurrent_llm_calls(monkeypatch):
    active = 0
    peak = 0

    async def fake_evaluate_dimension(bundle, dim, model_name, prompt, num_ctx=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return SimpleNamespace(dimension=dim, score=3, justification="", evidence_citations=[])

    monkeypatch.setattr(evaluator, "evaluate_dimension", fake_evaluate_dimension)

    async def run(limit: int) -> list:
        semaphore = asyncio.Semaphore(limit)
        bundle = ArtifactBundle(team_id="team", sprint_id="sprint")
        return await asyncio.gather(*(
            evaluator._bounded_evaluate(
                dim, bundle, "m", None, semaphore, {dim: ""}
            )
            for dim in evaluator.DIMENSIONS
        ))

    for limit in (1, 2, 4):
        peak = 0
        assert [r.dimension for r in asyncio.run(run(limit))] == list(evaluator.DIMENSIONS)
        assert peak == limit


def test_dimension_concurrency_env_is_clamped_to_at_least_one(monkeypatch):
    try:
        monkeypatch.setenv("LLM_DIMENSION_CONCURRENCY", "4")
        assert importlib.reload(evaluator).DIMENSION_CONCURRENCY == 4
        monkeypatch.setenv("LLM_DIMENSION_CONCURRENCY", "0")
        assert importlib.reload(evaluator).DIMENSION_CONCURRENCY == 1
    finally:
        monkeypatch.delenv("LLM_DIMENSION_CONCURRENCY", raising=False)
        importlib.reload(evaluator)


def test_log_gpu_offload_warns_on_partial_offload(monkeypatch, caplog):
    logged: dict = {}

    async def fake_snapshot():
        return [{"name": "sprintsight-r1-32b:latest", "size": 100, "size_vram": 60, "context_length": 16384, "offload_ratio": 0.6}]

    monkeypatch.setattr(evaluator, "snapshot_loaded_models", fake_snapshot)
    monkeypatch.setattr(evaluator.mlflow, "log_dict", lambda data, path: logged.setdefault("dict", (data, path)))
    monkeypatch.setattr(evaluator.mlflow, "log_metrics", lambda metrics: logged.setdefault("metrics", metrics))

    with caplog.at_level(logging.WARNING, logger="sprintsight.evaluator"):
        asyncio.run(evaluator._log_gpu_offload(ModelName.SPRINTSIGHT_R1_32B))

    assert logged["dict"][1] == "gpu/ollama_ps.json"
    assert logged["metrics"] == {"gpu_offload_ratio": 0.6, "gpu_model_vram_bytes": 60, "gpu_context_length": 16384}
    assert "only 60% on the GPU" in caplog.text


def test_log_gpu_offload_never_fails_the_assessment(monkeypatch, caplog):
    async def unreachable():
        raise httpx.ConnectError("tunnel down")

    monkeypatch.setattr(evaluator, "snapshot_loaded_models", unreachable)
    with caplog.at_level(logging.WARNING, logger="sprintsight.evaluator"):
        asyncio.run(evaluator._log_gpu_offload("sprintsight-qwen"))  # must not raise
    assert "Could not record GPU offload" in caplog.text
