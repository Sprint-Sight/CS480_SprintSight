"""MLflow run and trace handling that is safe for concurrent requests.

Why this exists. The fluent API (`mlflow.set_experiment`, `mlflow.start_run`,
`mlflow.log_metric`, ...) keeps its state in two places that concurrent requests share:

  * the *active-run stack*, which is thread-local. FastAPI runs every `async def` route on
    the same event-loop thread, so two assessments awaiting the LLM at the same time push
    and pop runs on one stack. One request's `end_run()` then ends the other's run, and
    `log_metric` lands on whichever run happens to be on top.
  * the *default experiment*, which is process-global. A request that targets another
    experiment changes where every other request's traces are written.

Nothing here touches either. A run is created through `MlflowClient` and every log call
names its `run_id`; the experiment for the traces is set per request through a
context-local trace destination (a ContextVar, so each request task has its own).

The judge worker (`judges/scheduler.py`) still uses the fluent API, which is fine: it runs
on its own thread, where the thread-local run stack is its own.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import mlflow
from mlflow import MlflowClient
from mlflow.entities.trace_location import MlflowExperimentLocation
from mlflow.tracing.constant import TraceMetadataKey
from mlflow.utils.mlflow_tags import MLFLOW_PARENT_RUN_ID

from llmops.mlflow_config import configure_mlflow, get_experiment_id

log = logging.getLogger(__name__)

_PARENT_RUN_TAG = MLFLOW_PARENT_RUN_ID


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


def route_traces_to_experiment(experiment_name: str) -> str:
    """Send the traces recorded in the *current context* to `experiment_name`.

    Context-local, so a concurrent request using a different experiment is unaffected.
    Returns the experiment id."""
    experiment_id = get_experiment_id(experiment_name)
    mlflow.tracing.set_destination(MlflowExperimentLocation(experiment_id), context_local=True)
    return experiment_id


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
    """Create a run through the client, terminate it on exit, and route this context's
    traces to the same experiment."""
    configure_mlflow()
    experiment_id = route_traces_to_experiment(experiment_name)
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
