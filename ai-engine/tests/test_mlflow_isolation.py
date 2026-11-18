"""The tests must not write into the real ai-engine/mlruns folder."""

import os
import uuid
from pathlib import Path

from mlflow import MlflowClient

REAL_MLRUNS = Path(__file__).resolve().parents[1] / "mlruns"


def _local_path(location: str) -> Path:
    return Path(location.removeprefix("file:///").removeprefix("file://")).resolve()


def test_a_new_experiment_keeps_its_artifacts_outside_the_real_mlruns_folder() -> None:
    """A SQLite tracking store defaults its artifact root to ./mlruns. conftest redirects it with
    a variable that is private to MLflow; this fails if an MLflow upgrade stops honouring it."""
    client = MlflowClient(tracking_uri=os.environ["MLFLOW_TRACKING_URI"])

    experiment_id = client.create_experiment(f"isolation-{uuid.uuid4().hex}")
    location = _local_path(client.get_experiment(experiment_id).artifact_location)

    assert REAL_MLRUNS not in location.parents
    assert Path(os.environ["_MLFLOW_SERVER_ARTIFACT_ROOT"]).resolve() in location.parents
