"""Where the judge finds the artifact bundle a trace was graded on.

The bundle is stored with the run that produced the trace (an MLflow run artifact), so a queued
judge job still finds it after the engine restarts or after more than _MAX newer assessments.
The in-memory registry is only a fast path for traces recorded before that artifact existed.
"""

import logging
from collections import OrderedDict

import mlflow

from schemas.artifact_bundle import ArtifactBundle

log = logging.getLogger(__name__)

BUNDLE_ARTIFACT = "artifact_bundle.json"
_MAX = 32
_BUNDLES: "OrderedDict[tuple[str, str], ArtifactBundle]" = OrderedDict()

def remember_bundle(bundle: ArtifactBundle) -> None:
    _BUNDLES[(bundle.team_id, bundle.sprint_id)] = bundle
    _BUNDLES.move_to_end((bundle.team_id, bundle.sprint_id))
    while len(_BUNDLES) > _MAX:
        _BUNDLES.popitem(last=False)

def get_bundle(team_id: str | None, sprint_id: str | None) -> ArtifactBundle | None:
    if team_id is None or sprint_id is None:
        return None
    return _BUNDLES.get((team_id, sprint_id))

def persist_bundle(run, bundle: ArtifactBundle) -> None:
    """Store `bundle` as an artifact of `run` (anything with log_dict). Never raises: a store
    that is down must not fail the assessment, it only leaves the judge to the in-memory copy."""
    try:
        run.log_dict(bundle.model_dump(mode="json"), BUNDLE_ARTIFACT)
    except Exception:  # best effort: never fail the assessment
        log.warning("Could not store the artifact bundle for team=%s sprint=%s; a judge job "
                    "queued across an engine restart will not find it.",
                    bundle.team_id, bundle.sprint_id, exc_info=True)

def load_persisted_bundle(run_id: str | None) -> ArtifactBundle | None:
    """The bundle stored with `run_id`, or None when there is none (a trace recorded before
    bundles were stored) or the store cannot be read."""
    if not run_id:
        return None
    try:
        return ArtifactBundle.model_validate(
            mlflow.artifacts.load_dict(f"runs:/{run_id}/{BUNDLE_ARTIFACT}"))
    except Exception:  # missing artifact, store down, or unreadable payload
        log.info("No stored artifact bundle for run %s.", run_id, exc_info=True)
        return None
