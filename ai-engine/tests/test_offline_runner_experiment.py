"""run_evaluation opens its MLflow run in the experiment it was asked for.

start_mlflow() stopped selecting an experiment in b95fb64, so a bare mlflow.start_run() in
the runner opened in MLflow's default experiment (MLFLOW_EXPERIMENT_NAME, which docker
compose sets to "sprintsight_experiment"). `cli analyze` only searches the requested
experiment, so it never saw those runs. These tests use a real (SQLite) MLflow store and set
MLFLOW_EXPERIMENT_NAME the way compose does.
"""

import mlflow
import pytest
from mlflow import MlflowClient

from evaluation.offline import analysis, runner
from llmops import mlflow_config

COMPOSE_DEFAULT = "sprintsight_experiment"


@pytest.fixture
def store(tmp_path, monkeypatch):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    previous = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    monkeypatch.setattr(mlflow_config, "_configured", True)  # do not re-point at MLFLOW_TRACKING_URI
    monkeypatch.setattr(mlflow_config, "_experiment_ids", {})
    client = MlflowClient(tracking_uri=uri)
    client.create_experiment(COMPOSE_DEFAULT, artifact_location=(tmp_path / "art-default").as_uri())
    monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", COMPOSE_DEFAULT)
    monkeypatch.chdir(tmp_path)  # the runner stages artifacts in a temp folder under the cwd
    yield client, tmp_path
    mlflow.set_tracking_uri(previous)


@pytest.fixture
def offline_runner(monkeypatch):
    """No Ollama, git or model calls: every example returns the same well-formed row."""

    async def fake_example(item, model, experiment_name):
        row = {
            "example_id": item.id,
            "format_valid": True,
            "error": None,
            "latency_s": 0.1,
            "dimension_completion_rate": 1.0,
        }
        return row, None, None

    monkeypatch.setattr(runner, "_run_one_example", fake_example)
    monkeypatch.setattr(runner, "model_digest", lambda model: None)
    monkeypatch.setattr(runner, "ollama_version", lambda: None)
    monkeypatch.setattr(runner, "git_sha", lambda: "unknown")


def test_run_lands_in_the_requested_experiment(store, offline_runner) -> None:
    client, tmp_path = store
    target = "model-comparison-under-test"  # does not exist yet: the runner creates it

    run_id = runner.run_evaluation(
        model="fake-model", dataset_name="d1_fixtures", subset=["high_performing"], experiment=target
    )

    experiment = client.get_experiment_by_name(target)
    assert experiment is not None
    run = client.get_run(run_id)
    assert run.info.experiment_id == experiment.experiment_id
    assert run.info.status == "FINISHED"
    assert run.data.params["dataset_name"] == "d1_fixtures"
    default_id = client.get_experiment_by_name(COMPOSE_DEFAULT).experiment_id
    assert client.search_runs([default_id]) == []
    assert mlflow.active_run() is None

    rows = analysis.load_runs(target, cache_dir=tmp_path / "cache")  # what `cli analyze` reads
    assert list(rows["mlflow_run_id"]) == [run_id]


def test_the_phase_tag_is_the_phase_you_asked_for(store, offline_runner) -> None:
    # Each dataset spec carries its own maturity label; it used to be tagged as `phase` after
    # --phase and overwrite it, so `--filter 'tags.phase = "final"'` never matched a final run.
    client, tmp_path = store

    run_id = runner.run_evaluation(
        model="fake-model", dataset_name="d1_fixtures", subset=["high_performing"],
        experiment="phase-under-test", phase="final",
    )

    run = client.get_run(run_id)
    assert run.data.params["phase"] == "final"
    assert run.data.tags["phase"] == "final"
    assert run.data.tags["dataset_phase"] == "smoke_test"  # the dataset's own label, kept apart
    rows = analysis.load_runs("phase-under-test", cache_dir=tmp_path / "cache")
    assert set(rows["phase"]) == {"final"}
    assert set(rows["dataset_hash"]) == {run.data.params["dataset_hash"]}
