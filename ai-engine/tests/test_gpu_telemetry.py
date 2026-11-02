import asyncio
import importlib
import json
import logging
from types import SimpleNamespace

import httpx

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
        return await asyncio.gather(*(
            # The fake ignores the bundle, so no real ArtifactBundle is needed.
            evaluator._bounded_evaluate(dim, None, "m", None, semaphore)  # type: ignore[arg-type]
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
    assert logged["metrics"] == {"gpu_offload_ratio": 0.6, "gpu_model_vram_bytes": 60}
    assert "only 60% on the GPU" in caplog.text


def test_log_gpu_offload_never_fails_the_assessment(monkeypatch, caplog):
    async def unreachable():
        raise httpx.ConnectError("tunnel down")

    monkeypatch.setattr(evaluator, "snapshot_loaded_models", unreachable)
    with caplog.at_level(logging.WARNING, logger="sprintsight.evaluator"):
        asyncio.run(evaluator._log_gpu_offload("sprintsight-qwen"))  # must not raise
    assert "Could not record GPU offload" in caplog.text
