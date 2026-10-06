"""Dataset abstraction for the preliminary model-comparison pipeline.

A dataset is a NAMED, HASHED collection of (example_id, ArtifactBundle)
items so a run from today ("d1_fixtures @ hash abc123…") can be told apart
from a run from next week ("d1_fixtures @ hash xyz789…" — someone edited a
fixture). The hash is logged with every MLflow run; the dataset name alone
is NOT enough provenance.

Adding a new dataset later:
    DATASETS["d2_real_sprints"] = _spec(
        description="Real anonymised sprints from CS203 2026",
        items=[
            DatasetItem(id="cs203-s1-team-a", bundle=load_real_bundle("..."))
            ...
        ],
    )

For now d1_fixtures mirrors schemas.benchmark_registry.FIXTURES verbatim so
we can get the pipeline running against data we already have. The pipeline
NEVER assumes a particular dataset size — a 3-item subset for a smoke test
is a valid dataset, just with less statistical power downstream.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from schemas.artifact_bundle import ArtifactBundle
from schemas.benchmark_registry import FIXTURES

log = logging.getLogger(__name__)

# Where on-disk real-sprint JSONs live by default. Override with the env
# var EVAL_REAL_SPRINTS_DIR when running from a different checkout. Kept
# relative to the ai-engine root so a fresh clone of the repo gets the
# same path without local config.
_DEFAULT_REAL_SPRINTS_DIR = Path("research/eval/data/real_sprints")
_REAL_SPRINTS_DIR_ENV = "EVAL_REAL_SPRINTS_DIR"


@dataclass(frozen=True)
class DatasetItem:
    id: str
    bundle: ArtifactBundle


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    description: str
    # Lazy factory, not an eager list: Dataset 2 and 3 may need I/O that
    # isn't desirable at import time. Factories must be deterministic — same
    # call must produce items in the same order with the same contents, or
    # the hash changes between runs.
    load: Callable[[], list[DatasetItem]]
    tags: dict[str, str] = field(default_factory=dict)


def _canonical_item_json(item: DatasetItem) -> str:
    # Serialise via Pydantic to get a stable, mode-controlled representation,
    # then sort keys in the final JSON dump so dict ordering can't affect the
    # hash. ensure_ascii keeps the hash stable across platforms with
    # different default encodings.
    bundle_dict = item.bundle.model_dump(mode="json")
    payload = {"id": item.id, "bundle": bundle_dict}
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def dataset_hash(items: list[DatasetItem]) -> str:
    """Hash of the dataset's content in order. Order matters: a reshuffled
    dataset is a different dataset for reproducibility purposes."""
    hasher = hashlib.sha256()
    for item in items:
        hasher.update(_canonical_item_json(item).encode("utf-8"))
        hasher.update(b"\n")  # Record separator keeps items unambiguous
    return hasher.hexdigest()[:16]


def _load_d1_fixtures() -> list[DatasetItem]:
    # Keep ordering fixed and alphabetical by key so the hash is stable
    # even if someone reorders schemas.benchmark_registry.FIXTURES later.
    return [DatasetItem(id=key, bundle=FIXTURES[key]) for key in sorted(FIXTURES)]


def _real_sprints_dir() -> Path:
    override = os.getenv(_REAL_SPRINTS_DIR_ENV)
    return Path(override) if override else _DEFAULT_REAL_SPRINTS_DIR


def _load_bundle_from_file(path: Path) -> ArtifactBundle:
    """Read one JSON file and rehydrate it into an ArtifactBundle.

    The file must be a dump of `ArtifactBundle.model_dump(mode="json")`
    (what backend/scripts/export_eval_bundles.py writes). Validation is
    strict so a malformed export fails fast — a silently-skipped example
    would quietly change the dataset hash later when it starts loading.
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return ArtifactBundle.model_validate(data)


def _load_real_sprints() -> list[DatasetItem]:
    """Load every *.json file in the real-sprints directory, sorted by
    filename for a stable hash. The example `id` is the filename without
    extension — pick file names that mean something (e.g.
    `cs203_proj_a_sprint_1.json`), because they become the x-axis labels
    in every subsequent plot and the merge key for judge scores.
    """
    directory = _real_sprints_dir()
    if not directory.is_dir():
        raise FileNotFoundError(
            f"Real-sprints directory not found: {directory}. "
            f"Set {_REAL_SPRINTS_DIR_ENV} or export sprints there via "
            f"backend/scripts/export_eval_bundles.py."
        )
    files = sorted(directory.glob("*.json"))
    if not files:
        raise FileNotFoundError(
            f"No *.json files in {directory}. Export sprints there first via "
            f"backend/scripts/export_eval_bundles.py."
        )
    items: list[DatasetItem] = []
    for path in files:
        try:
            bundle = _load_bundle_from_file(path)
        except Exception as exc:
            raise ValueError(f"Failed to parse {path.name} as ArtifactBundle: {exc}") from exc
        items.append(DatasetItem(id=path.stem, bundle=bundle))
    log.info("Loaded %d real-sprint bundle(s) from %s.", len(items), directory)
    return items


DATASETS: dict[str, DatasetSpec] = {
    "d1_fixtures": DatasetSpec(
        name="d1_fixtures",
        description=(
            "Dataset 1 (synthetic) - 5 hand-crafted sprint fixtures from "
            "schemas.fixtures covering the full performance spectrum "
            "(high_performing -> struggling). SMOKE-TEST ONLY: use this to "
            "sanity-check the pipeline wiring, NOT for any claim in the "
            "report. Prefer d_real_sprints for real evaluation."
        ),
        load=_load_d1_fixtures,
        tags={"source": "fixtures", "phase": "smoke_test"},
    ),
    "d_real_sprints": DatasetSpec(
        name="d_real_sprints",
        description=(
            "Real sprints exported from the SprintSight backend's Postgres "
            "via backend/scripts/export_eval_bundles.py. One JSON file per "
            "(course_id, project_id, sprint_id) in "
            "research/eval/data/real_sprints/ (override with "
            f"{_REAL_SPRINTS_DIR_ENV} env var). Size grows as more sprints "
            "are exported; the dataset hash changes with every addition, so "
            "the report must cite the hash alongside the dataset name."
        ),
        load=_load_real_sprints,
        tags={"source": "backend_postgres", "phase": "preliminary"},
    ),
    # Add d_real_sprints_held_out, d_real_sprints_final, etc. by pointing a
    # different EVAL_REAL_SPRINTS_DIR at a separate directory and registering
    # another spec here. Separate directories prevent accidental mixing of
    # dev/held-out partitions.
}


def load_dataset(name: str, subset: list[str] | None = None) -> tuple[list[DatasetItem], str, DatasetSpec]:
    """Load a dataset by name; optionally restrict to a subset of example IDs.

    Returns (items, hash, spec). The hash is computed over the ACTUALLY
    loaded items — so running against a subset gets its own hash, and a
    later full-dataset run gets a different hash. That's deliberate: subset
    runs and full-dataset runs are different experimental conditions and
    the analysis layer must be able to tell them apart.
    """
    if name not in DATASETS:
        available = ", ".join(sorted(DATASETS)) or "(none registered)"
        raise KeyError(f"Unknown dataset '{name}'. Available: {available}.")
    spec = DATASETS[name]
    items = spec.load()
    if subset is not None:
        selected = set(subset)
        items = [item for item in items if item.id in selected]
        missing = selected - {item.id for item in items}
        if missing:
            raise KeyError(f"Dataset '{name}' is missing requested IDs: {sorted(missing)}")
    return items, dataset_hash(items), spec


def list_datasets() -> list[tuple[str, str]]:
    """(name, description) tuples for CLI help / report."""
    return [(name, spec.description) for name, spec in DATASETS.items()]
