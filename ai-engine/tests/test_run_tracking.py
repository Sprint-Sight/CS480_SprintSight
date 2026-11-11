"""Client-managed runs stay isolated when requests interleave on one thread.

FastAPI runs every async route on the same event-loop thread. The fluent
mlflow.start_run keeps its run stack per *thread*, so two interleaved assessments used to
share it. These tests run two requests concurrently on one thread against a real (SQLite)
MLflow store.
"""

import asyncio

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.tracing.constant import TraceMetadataKey
from mlflow.utils.mlflow_tags import MLFLOW_PARENT_RUN_ID

from llmops import mlflow_config
from llmops.run_tracking import tracked_run


@pytest.fixture
def store(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    monkeypatch.setattr(mlflow_config, "_configured", True)  # do not re-point at MLFLOW_TRACKING_URI
    monkeypatch.setattr(mlflow_config, "_experiment_ids", {})
    client = MlflowClient(tracking_uri=uri)
    ids = {
        name: client.create_experiment(name, artifact_location=str(tmp_path / f"art-{name}"))
        for name in ("exp-a", "exp-b")
    }
    yield client, ids
    mlflow.flush_trace_async_logging()
    mlflow.set_tracking_uri(previous)


async def _request(client, experiment, label, delay):
    with tracked_run(client, experiment, f"run-{label}") as run, mlflow.start_span(name=f"root-{label}") as root:
        run.link_current_trace()
        await asyncio.sleep(delay)  # let the other request interleave
        run.log_param("who", label)
        run.log_metric("value", 1.0 if label == "A" else 2.0)
        await asyncio.sleep(delay)
        trace_id = root.trace_id
    return run.run_id, trace_id


def _eventually(fetch, what: str, timeout: float = 60.0):
    """Return fetch() once it is truthy, flushing MLflow's async trace export between tries.

    Traces are exported on background threads, so one flush followed by one search is not
    guaranteed to see them: it passed locally and failed on a slower CI runner. Polling for a
    bounded time makes the test wait for what it needs and still fail, with a clear message,
    if the trace never arrives."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        mlflow.flush_trace_async_logging()
        found = fetch()
        if found:
            return found
        if time.monotonic() >= deadline:
            raise AssertionError(f"{what} did not appear within {timeout:.0f}s")
        time.sleep(0.5)


def test_concurrent_requests_do_not_share_runs_or_experiments(store) -> None:
    client, ids = store

    async def scenario():
        return await asyncio.gather(
            _request(client, "exp-a", "A", 0.2), _request(client, "exp-b", "B", 0.1)
        )

    (run_a, trace_a), (run_b, trace_b) = asyncio.run(scenario())
    expected = {ids["exp-a"]: trace_a, ids["exp-b"]: trace_b}

    def both_traces_are_stored_and_linked() -> bool:
        for experiment_id, trace_id in expected.items():
            stored = {t.info.trace_id: t for t in client.search_traces(locations=[experiment_id])}
            if trace_id not in stored or "mlflow.sourceRun" not in stored[trace_id].info.trace_metadata:
                return False
        return True

    _eventually(both_traces_are_stored_and_linked, "both requests' traces")

    for run_id, trace_id, label, own, other in (
        (run_a, trace_a, "A", ids["exp-a"], ids["exp-b"]),
        (run_b, trace_b, "B", ids["exp-b"], ids["exp-a"]),
    ):
        run = client.get_run(run_id)
        assert run.info.experiment_id == own
        assert run.info.status == "FINISHED"
        assert run.data.params == {"who": label}
        assert run.data.metrics["value"] == (1.0 if label == "A" else 2.0)
        own_traces = client.search_traces(locations=[own])
        assert trace_id in [t.info.trace_id for t in own_traces]
        assert trace_id not in [t.info.trace_id for t in client.search_traces(locations=[other])]
        linked = next(t for t in own_traces if t.info.trace_id == trace_id)
        assert linked.info.trace_metadata[TraceMetadataKey.SOURCE_RUN] == run_id

    assert mlflow.active_run() is None  # nothing was pushed onto the shared run stack


def test_a_failing_request_marks_its_run_failed_and_reraises(store) -> None:
    client, _ = store
    captured = {}

    def fail() -> None:
        with tracked_run(client, "exp-a", "doomed") as run:
            captured["run_id"] = run.run_id
            raise RuntimeError("model gone")

    with pytest.raises(RuntimeError, match="model gone"):
        fail()

    assert client.get_run(captured["run_id"]).info.status == "FAILED"


def test_a_run_started_by_the_caller_becomes_the_parent(store) -> None:
    # research scripts wrap evaluate_sprint in their own run; the old nested=True kept that tree
    client, _ = store
    with mlflow.start_run(experiment_id=store[1]["exp-a"]) as outer, tracked_run(client, "exp-a", "child") as child:
        pass
    assert client.get_run(child.run_id).data.tags[MLFLOW_PARENT_RUN_ID] == outer.info.run_id


def test_eventually_waits_for_a_late_result_and_otherwise_fails_clearly(monkeypatch) -> None:
    monkeypatch.setattr(mlflow, "flush_trace_async_logging", lambda: None)
    answers = iter([None, None, "ready"])  # the trace shows up on the third look

    assert _eventually(lambda: next(answers), "the trace") == "ready"
    with pytest.raises(AssertionError, match="the trace did not appear within 1s"):
        _eventually(lambda: None, "the trace", timeout=1.0)
