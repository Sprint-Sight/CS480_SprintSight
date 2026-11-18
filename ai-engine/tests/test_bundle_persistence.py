"""The judge finds the bundle a trace was graded on without the in-memory registry (H5)."""

from types import SimpleNamespace

import mlflow
import pytest
from mlflow import MlflowClient
from mlflow.tracing.constant import TraceMetadataKey

from evaluation.judges.citation_grounding import _bundle_of
from llmops import mlflow_config
from llmops.run_tracking import TrackedRun
from schemas import bundle_registry
from schemas.artifact_bundle import ArtifactBundle
from schemas.bundle_registry import (
    BUNDLE_ARTIFACT,
    load_persisted_bundle,
    persist_bundle,
    remember_bundle,
)


def make_bundle(instructor_expectations: str = "None.") -> ArtifactBundle:
    return ArtifactBundle(
        team_id="team-z", sprint_id="s9", commits=[], jira_tickets=[], peer_evaluations=[],
        collaboration_metrics={}, artifact_metrics={}, project_context_documents=[],
        repo_snapshot=None, instructor_expectations=instructor_expectations,
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    monkeypatch.setattr(mlflow_config, "_configured", True)
    monkeypatch.setattr(mlflow_config, "_experiment_ids", {})
    client = MlflowClient(tracking_uri=uri)
    experiment_id = client.create_experiment("exp", artifact_location=str(tmp_path / "art"))
    bundle_registry._BUNDLES.clear()
    yield client, experiment_id
    bundle_registry._BUNDLES.clear()
    mlflow.set_tracking_uri(previous)


def new_run(store) -> TrackedRun:
    client, experiment_id = store
    created = client.create_run(experiment_id)
    return TrackedRun(client, created.info.run_id, experiment_id)


def trace_of(run_id: str | None, sprint_id: str | None = "s9") -> SimpleNamespace:
    metadata = {TraceMetadataKey.SOURCE_RUN: run_id} if run_id else {}
    root = SimpleNamespace(parent_id=None, inputs={"sprint_id": sprint_id})
    return SimpleNamespace(info=SimpleNamespace(trace_metadata=metadata), data=SimpleNamespace(spans=[root]))


def test_a_stored_bundle_round_trips(store) -> None:
    run = new_run(store)

    persist_bundle(run, make_bundle())

    assert load_persisted_bundle(run.run_id) == make_bundle()


def test_nothing_stored_is_not_an_error(store) -> None:
    assert load_persisted_bundle(None) is None
    assert load_persisted_bundle(new_run(store).run_id) is None  # a trace from before bundles were stored
    assert load_persisted_bundle("no-such-run") is None


def test_a_store_that_fails_never_fails_the_assessment() -> None:
    class DownStore:
        def log_dict(self, dictionary, artifact_file):
            raise ConnectionError("artifact store is down")

    persist_bundle(DownStore(), make_bundle())  # must not raise


def test_the_judge_reads_the_stored_bundle_when_the_registry_is_empty(store) -> None:
    run = new_run(store)
    persist_bundle(run, make_bundle())

    assert _bundle_of(trace_of(run.run_id), "team-z") == make_bundle()


def test_the_stored_bundle_wins_over_a_newer_run_of_the_same_sprint(store) -> None:
    """The registry is keyed by team and sprint, so a re-run replaces what an older job needs."""
    run = new_run(store)
    graded = make_bundle("What this trace was graded on.")
    persist_bundle(run, graded)
    remember_bundle(make_bundle("A later re-run of the same sprint."))

    assert _bundle_of(trace_of(run.run_id), "team-z") == graded


def test_a_trace_without_a_stored_bundle_still_uses_the_registry(store) -> None:
    remember_bundle(make_bundle())

    assert _bundle_of(trace_of(None), "team-z") == make_bundle()


def test_no_bundle_anywhere_is_still_a_clear_error(store) -> None:
    with pytest.raises(KeyError, match="no bundle"):
        _bundle_of(trace_of(None, "unknown-sprint"), "unknown-team")


def test_the_artifact_name_is_stable() -> None:
    assert BUNDLE_ARTIFACT == "artifact_bundle.json"
