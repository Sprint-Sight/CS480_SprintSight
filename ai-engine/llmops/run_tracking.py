"""MLflow run and trace handling for requests that overlap on one event loop.

Why this exists. The fluent API (`mlflow.set_experiment`, `mlflow.start_run`,
`mlflow.log_metric`, ...) keeps its state in two places that concurrent requests share:

  * the *active-run stack*, which is thread-local. FastAPI runs every `async def` route on
    the same event-loop thread, so two assessments awaiting the LLM at the same time push
    and pop runs on one stack. One request's `end_run()` then ends the other's run, and
    `log_metric` lands on whichever run happens to be on top.
  * the *default experiment*, which is process-global. A request that targets another
    experiment changes where every other request's traces are written.

Runs are therefore created through `MlflowClient` and every log call names its `run_id`
(`tracked_run`). That part is genuinely concurrency-safe: any number of runs can be open at once.

Traces are different, and `mlflow.tracing.set_destination(..., context_local=True)` does NOT make
them safe. `context_local` scopes only the destination *value*; the tracer provider behind it is a
single process-wide object, and every `set_destination` call rebuilds it and shuts down the old
one's span processors. A second request calling it while the first is still running therefore
drops the first request's remaining spans ("Processor is already shutdown, ignoring call"), so its
trace is lost or arrives unlinked. This showed up as a test that passed on a developer machine
and failed on CI, and it would lose traces in production whenever two assessments overlapped.

`exclusive_trace_destination` is the fix: the shared provider is re-pointed only while holding a
lock, and the lock is held for the whole traced section, so it is never rebuilt under in-flight
spans. Assessments are serialised from this point, which costs little: the model server runs
them one at a time anyway.

The judge worker (`evaluation/online/scheduler.py`) still uses the fluent API on its own thread. It
does not overlap with grading (the model-slot arbiter keeps them apart), so it never sees a
provider being rebuilt under it.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.entities.trace_location import MlflowExperimentLocation
from mlflow.tracing.constant import TraceMetadataKey
from mlflow.utils.mlflow_tags import MLFLOW_PARENT_RUN_ID

from llmops.mlflow_config import configure_mlflow, get_experiment_id

log = logging.getLogger(__name__)

_PARENT_RUN_TAG = MLFLOW_PARENT_RUN_ID

# One lock per event loop. An asyncio.Lock must not be shared between loops, and a threading.Lock
# held across awaits would block the loop for every other task.
_destination_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


class TrackedRun:
    """A run that is addressed by id on every call, never through the active-run stack."""

    def __init__(self, client: MlflowClient, run_id: str, experiment_id: str) -> None:
        self.client = client
        self.run_id = run_id
        self.experiment_id = experiment_id

    def log_param(self, key: str, value: Any) -> None:
        self.client.log_param(self.run_id, key, value)

    def log_params(self, params: Mapping[str, Any]) -> None:
        for key, value in params.items():
            self.log_param(key, value)

    def log_metric(self, key: str, value: float) -> None:
        self.client.log_metric(self.run_id, key, value)

    def log_metrics(self, metrics: Mapping[str, float]) -> None:
        for key, value in metrics.items():
            self.log_metric(key, value)

    def log_dict(self, dictionary: dict, artifact_file: str) -> None:
        self.client.log_dict(self.run_id, dictionary, artifact_file)

    def log_artifact(self, local_path: str, artifact_path: str | None = None) -> None:
        self.client.log_artifact(self.run_id, local_path, artifact_path)

    def set_tag(self, key: str, value: Any) -> None:
        self.client.set_tag(self.run_id, key, value)

    def link_current_trace(self) -> None:
        """Associate the trace being recorded by the current span with this run, which is
        what the fluent API did implicitly through the active run."""
        mlflow.update_current_trace(metadata={TraceMetadataKey.SOURCE_RUN: self.run_id})


def _destination_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _destination_locks.get(loop)
    if lock is None:
        lock = _destination_locks[loop] = asyncio.Lock()
    return lock


@asynccontextmanager
async def exclusive_trace_destination(experiment_name: str) -> AsyncIterator[str]:
    """Record the traces of the enclosed block in `experiment_name`, one block at a time.

    Waits for any other block to finish, then points the shared tracer provider at the experiment
    (context-local, so the judge's thread is unaffected) and holds the lock until the block ends.
    Yields the experiment id. Cancellation while waiting just leaves the queue."""
    async with _destination_lock():
        configure_mlflow()
        experiment_id = get_experiment_id(experiment_name)
        mlflow.tracing.set_destination(MlflowExperimentLocation(experiment_id), context_local=True)
        yield experiment_id


def _caller_active_run_id() -> str | None:
    """Run id of a run the *caller* opened with the fluent API (research scripts wrap
    `evaluate_sprint` in `mlflow.start_run`). Read-only: it only decides whether the new run
    is nested under it, as `start_run(nested=True)` used to do."""
    active = mlflow.active_run()
    return active.info.run_id if active is not None else None


@contextmanager
def tracked_run(
    client: MlflowClient,
    experiment_name: str,
    run_name: str,
    *,
    tags: Mapping[str, str] | None = None,
) -> Iterator[TrackedRun]:
    """Create a run through the client and terminate it on exit (FAILED if the block raises or is
    cancelled). Safe to use concurrently. It does not route traces: wrap the traced section in
    `exclusive_trace_destination` for that."""
    configure_mlflow()
    experiment_id = get_experiment_id(experiment_name)
    run_tags = dict(tags or {})
    parent = _caller_active_run_id()
    if parent is not None:
        run_tags[_PARENT_RUN_TAG] = parent
    created = client.create_run(experiment_id, run_name=run_name, tags=run_tags or None)
    run = TrackedRun(client, created.info.run_id, experiment_id)
    status = "FINISHED"
    try:
        yield run
    except BaseException:
        status = "FAILED"
        raise
    finally:
        try:
            client.set_terminated(run.run_id, status)
        except Exception:
            log.warning("Could not terminate MLflow run %s as %s.", run.run_id, status, exc_info=True)
