"""
schemas/benchmark_registry.py

Maps each benchmark fixture's key to its ArtifactBundle, so callers (e.g.
judges/custom_llm_judge.py's scorer, which only receives plain JSON-able
inputs from MLflow) can look up "which bundle produced this assessment" by
fixture_key instead of importing schemas.fixtures directly. Keys match
research/validation_harness.py's FIXTURE_CANDIDATES and schemas/benchmark.py's
gold fixtures.
"""

from schemas.artifact_bundle import ArtifactBundle
from schemas.fixtures import (
    good_collab_low_output_team,
    high_performing_team,
    imbalanced_high_output_team,
    lone_contributor_poor_outcome_team,
    struggling_team,
)

FIXTURES: dict[str, ArtifactBundle] = {
    "high_performing": high_performing_team,
    "struggling": struggling_team,
    "good_collab_low_output": good_collab_low_output_team,
    "imbalanced_high_output": imbalanced_high_output_team,
    "lone_contributor_poor_outcome": lone_contributor_poor_outcome_team,
}
