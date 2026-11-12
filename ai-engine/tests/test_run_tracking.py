"""Overlapping assessments keep their own runs and their own traces.

FastAPI runs every async route on one event-loop thread, so two assessments can be in flight at
once. Runs are client-managed and independent; traces share one process-wide tracer provider, so
they are recorded one assessment at a time (llmops/run_tracking.py). These tests run overlapping
requests against a real (SQLite) MLflow store.
"""

import asyncio
import time

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.tracing.constant import TraceMetadataKey
from mlflow.utils.mlflow_tags import MLFLOW_PARENT_RUN_ID

from llmops import mlflow_config
from llmops.run_tracking import exclusive_trace_destination, tracked_run


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


async def _request(client, experiment, label, delay, events=None):
    """One assessment as the evaluator runs it: hold the trace destination, open a run, trace."""
    async with exclusive_trace_destination(experiment):
        with tracked_run(client, experiment, f"run-{label}") as run, mlflow.start_span(name=f"root-{label}") as root:
            run.link_current_trace()
            if events is not None:
                events.append(f"{label} start")
            await asyncio.sleep(delay)  # long enough for the other requests to arrive
            run.log_param("who", label)
            run.log_metric("value", 1.0 if label == "A" else 2.0)
            with mlflow.start_span(name=f"child-{label}"):  # a span that is open when others arrive
                await asyncio.sleep(delay)
            trace_id = root.trace_id
            if events is not None:
                events.append(f"{label} end")
    return run.run_id, trace_id


def _eventually(fetch, what: str, timeout: float = 60.0):
    """Return fetch() once it is truthy, flushing MLflow's async trace export between tries.

    Traces are exported on background threads, so one flush followed by one search is not
    guaranteed to see them. Polling for a bounded time makes the test wait for what it needs and
    still fail, with a clear message, if the trace never arrives."""
    deadline = time.monotonic() + timeout
    while True:
        mlflow.flush_trace_async_logging()
        found = fetch()
        if found:
            return found
        if time.monotonic() >= deadline:
            raise AssertionError(f"{what} did not appear within {timeout:.0f}s")
        time.sleep(0.5)


def _stored_and_linked(client, expected: dict[str, str]) -> bool:
    """Is every trace in {trace_id: experiment_id} searchable in its experiment and linked to a run?"""
    for trace_id, experiment_id in expected.items():
        stored = {t.info.trace_id: t for t in client.search_traces(locations=[experiment_id])}
        if trace_id not in stored or TraceMetadataKey.SOURCE_RUN not in stored[trace_id].info.trace_metadata:
            return False
    return True


def test_concurrent_requests_in_different_experiments_keep_their_own_runs_and_traces(store) -> None:
    client, ids = store

    async def scenario():
        return await asyncio.gather(
            _request(client, "exp-a", "A", 0.2), _request(client, "exp-b", "B", 0.1)
        )

    (run_a, trace_a), (run_b, trace_b) = asyncio.run(scenario())
    expected = {trace_a: ids["exp-a"], trace_b: ids["exp-b"]}
    _eventually(lambda: _stored_and_linked(client, expected), "both requests' traces")

    for run_id, trace_id, label, own, other in (
        (run_a, trace_a, "A", ids["exp-a"], ids["exp-b"]),
        (run_b, trace_b, "B", ids["exp-b"], ids["exp-a"]),
    ):
        run = client.get_run(run_id)
        assert run.info.experiment_id == own
        assert run.info.status == "FINISHED"
        assert run.data.params == {"who": label}
        assert run.data.metrics["value"] == (1.0 if label == "A" else 2.0)
        assert trace_id not in [t.info.trace_id for t in client.search_traces(locations=[other])]
        linked = next(t for t in client.search_traces(locations=[own]) if t.info.trace_id == trace_id)
        assert linked.info.trace_metadata[TraceMetadataKey.SOURCE_RUN] == run_id

    assert mlflow.active_run() is None  # nothing was pushed onto the shared run stack


def test_overlapping_requests_in_the_same_experiment_all_keep_their_traces(store) -> None:
    # The production case: every assessment targets the default experiment, and a second one can
    # arrive while the first is still grading. Re-pointing MLflow's shared tracer provider under
    # the first one's open spans used to drop its trace.
    client, ids = store

    async def scenario():
        return await asyncio.gather(*(_request(client, "exp-a", label, 0.15) for label in ("A", "B", "C")))

    results = asyncio.run(scenario())
    expected = {trace_id: ids["exp-a"] for _, trace_id in results}
    _eventually(lambda: _stored_and_linked(client, expected), "all three requests' traces")

    assert len(expected) == 3
    for run_id, trace_id in results:
        linked = next(t for t in client.search_traces(locations=[ids["exp-a"]]) if t.info.trace_id == trace_id)
        assert linked.info.trace_metadata[TraceMetadataKey.SOURCE_RUN] == run_id
        assert client.get_run(run_id).info.status == "FINISHED"


def test_requests_hold_the_trace_destination_one_at_a_time(store) -> None:
    client, _ = store
    events: list[str] = []

    async def scenario():
        await asyncio.gather(*(_request(client, "exp-a", label, 0.1, events) for label in ("A", "B", "C")))

    asyncio.run(scenario())

    assert events == ["A start", "A end", "B start", "B end", "C start", "C end"]  # never interleaved


def test_a_request_waiting_for_its_turn_can_be_cancelled_and_the_next_still_runs(store) -> None:
    client, ids = store
    events: list[str] = []

    async def scenario():
        first = asyncio.ensure_future(_request(client, "exp-a", "A", 0.3, events))
        await asyncio.sleep(0.05)
        abandoned = asyncio.ensure_future(_request(client, "exp-a", "B", 0.1, events))  # queued behind A
        third = asyncio.ensure_future(_request(client, "exp-a", "C", 0.1, events))
        await asyncio.sleep(0.05)
        abandoned.cancel()  # e.g. the backend gave up on it (api/disconnect.py)
        with pytest.raises(asyncio.CancelledError):
            await abandoned
        return await first, await third

    (_, trace_a), (_, trace_c) = asyncio.run(scenario())

    assert events == ["A start", "A end", "C start", "C end"]  # B never started and did not block C
    _eventually(lambda: _stored_and_linked(client, {trace_a: ids["exp-a"], trace_c: ids["exp-a"]}), "A's and C's traces")


def test_a_failing_request_marks_its_run_failed_reraises_and_frees_the_destination(store) -> None:
    client, ids = store
    captured: dict[str, str] = {}

    async def failing():
        async with exclusive_trace_destination("exp-a"):
            with tracked_run(client, "exp-a", "doomed") as run:
                captured["run_id"] = run.run_id
                raise RuntimeError("model gone")

    async def scenario():
        with pytest.raises(RuntimeError, match="model gone"):
            await failing()
        # the lock was released: this does not wait
        return await asyncio.wait_for(_request(client, "exp-a", "A", 0.05), timeout=15)

    _, trace_id = asyncio.run(scenario())

    assert client.get_run(captured["run_id"]).info.status == "FAILED"
    _eventually(lambda: _stored_and_linked(client, {trace_id: ids["exp-a"]}), "the next request's trace")


def test_a_run_started_by_the_caller_becomes_the_parent(store) -> None:
    # research scripts wrap evaluate_sprint in their own run; the old nested=True kept that tree
    client, _ = store
    with mlflow.start_run(experiment_id=store[1]["exp-a"]) as outer, tracked_run(client, "exp-a", "child") as child:
        pass
    assert client.get_run(child.run_id).data.tags[MLFLOW_PARENT_RUN_ID] == outer.info.run_id


def test_the_destination_lock_works_across_separate_event_loops(store) -> None:
    # scripts and tests call asyncio.run repeatedly; a lock tied to the first loop would break the second
    client, ids = store

    for label in ("A", "B"):
        _, trace_id = asyncio.run(_request(client, "exp-a", label, 0.05))
        _eventually(lambda t=trace_id: _stored_and_linked(client, {t: ids["exp-a"]}), f"request {label}'s trace")


def test_eventually_waits_for_a_late_result_and_otherwise_fails_clearly(monkeypatch) -> None:
    monkeypatch.setattr(mlflow, "flush_trace_async_logging", lambda: None)
    answers = iter([None, None, "ready"])  # the trace shows up on the third look

    assert _eventually(lambda: next(answers), "the trace") == "ready"
    with pytest.raises(AssertionError, match="the trace did not appear within 1s"):
        _eventually(lambda: None, "the trace", timeout=1.0)
