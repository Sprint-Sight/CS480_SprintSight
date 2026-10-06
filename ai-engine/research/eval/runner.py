"""The one-run API for the model-comparison pipeline.

A "run" here = (model × dataset × prompt_version × seed), one MLflow run,
one per-example JSONL artifact. That granularity is deliberate — see
research/eval/README.md for why we do NOT create a nested MLflow run per
example.

Public entry:

    run_evaluation(
        model="sprintsight-qwen",
        dataset_name="d1_fixtures",
        prompt_version="v1.0",
        seed=42,
        experiment="sprintsight-model-comparison",
    )

Everything about reproducibility (git SHA, model digest, dataset hash,
prompt hash, Ollama version) is captured as MLflow params. The analysis
layer only trusts data pulled from MLflow runs; it does NOT scan loose
JSONL files on disk, so if a result isn't in MLflow it doesn't exist for
the report.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import mlflow
import pandas as pd

from llmops.mlflow_config import start_mlflow
from prompts.dimension_criteria import DIMENSION_PROMPTS
from prompts.templates import render_dimension_prompt
from research.eval.datasets import DatasetItem, load_dataset
from research.eval.metrics import summarise_example
from services.evaluator import evaluate_sprint

log = logging.getLogger(__name__)

DEFAULT_EXPERIMENT = "sprintsight-model-comparison"


# ---------- Reproducibility helpers ----------------------------------------

def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def _ollama_version() -> str | None:
    try:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
        resp = httpx.get(f"{base}/api/version", timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("version")
    except Exception:
        return None


def _model_digest(model_name: str) -> str | None:
    """Short digest of the Ollama model manifest. Pins the exact weights/
    quantisation your run used — critical when the same tag can be
    re-pulled with different quantisation later."""
    try:
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
        resp = httpx.post(f"{base}/api/show", json={"name": model_name}, timeout=10.0)
        resp.raise_for_status()
        digest = resp.json().get("digest") or resp.json().get("model_info", {}).get("general.digest")
        return (digest or "")[:16] or None
    except Exception:
        return None


def _prompt_hash(prompt_version: str) -> str:
    """Hash the ACTUAL rendered dimension prompts for the current prompt
    version so a textual tweak in prompts/templates.py produces a new hash
    without anyone having to remember to bump prompt_version."""
    hasher = hashlib.sha256()
    hasher.update(prompt_version.encode())
    for dim, criteria in sorted(DIMENSION_PROMPTS.items()):
        rendered = render_dimension_prompt(dim, criteria, "<bundle>", "<facts>", "<context>")
        hasher.update(rendered.encode("utf-8"))
    return hasher.hexdigest()[:16]


# ---------- Run config and result dataclasses ------------------------------

@dataclass
class RunConfig:
    model: str
    dataset_name: str
    prompt_version: str = "v1.0"
    seed: int | None = None
    repeats: int = 1
    subset: list[str] | None = None
    experiment: str = DEFAULT_EXPERIMENT
    phase: str = "preliminary"
    extra_tags: dict[str, str] = field(default_factory=dict)
    note: str = ""


# ---------- The runner ------------------------------------------------------

async def _run_one_example(item: DatasetItem, model: str) -> tuple[dict, Any, str | None]:
    """Evaluate ONE example on the given model. Returns (per_example_row,
    raw_assessment_json_or_None, error_or_None).

    Timing captures wall clock around evaluate_sprint only — not around
    the metric computation that follows. Latency numbers in the report
    should reflect what the production AI engine actually spends.
    """
    t0 = time.perf_counter()
    error: str | None = None
    assessment = None
    try:
        assessment = await evaluate_sprint(item.bundle, model)
    except Exception as exc:  # noqa: BLE001 - the eval must survive a model failure
        error = f"{type(exc).__name__}: {exc}"
        log.exception("evaluate_sprint failed for example=%s model=%s", item.id, model)
    latency_s = time.perf_counter() - t0

    row = summarise_example(item.bundle, assessment, error)
    row["example_id"] = item.id
    row["latency_s"] = latency_s
    # Token accounting is not currently surfaced by evaluator.py — fill in
    # later from the audit logs if needed; keep the column so analysis
    # schemas don't drift.
    row["tokens_prompt"] = None
    row["tokens_completion"] = None
    row["tokens_total"] = None

    raw = assessment.model_dump(mode="json") if assessment is not None else None
    return row, raw, error


def _aggregate(rows: list[dict]) -> dict[str, float]:
    """Run-level aggregates. Only numeric aggregates land in MLflow metrics;
    distributional stuff stays in the per_example artifact for analysis."""
    df = pd.DataFrame(rows)
    n = len(df)
    out: dict[str, float] = {
        "n_examples": float(n),
        "format_validity_rate": float(df["format_valid"].mean()) if n else 0.0,
        "error_rate": float(df["error"].notna().mean()) if n else 0.0,
        "latency_mean_s": float(df["latency_s"].mean()) if n else 0.0,
        "latency_median_s": float(df["latency_s"].median()) if n else 0.0,
        "latency_p95_s": float(df["latency_s"].quantile(0.95)) if n else 0.0,
        "dimension_completion_rate_mean": float(df["dimension_completion_rate"].mean()) if n else 0.0,
    }
    # groundedness/overall_score skip-None aggregates so a totally-failed
    # run doesn't poison the metric column
    for metric in ("groundedness_rate", "overall_score", "raw_rubric_average"):
        values = df[metric].dropna()
        out[f"{metric}_mean"] = float(values.mean()) if not values.empty else float("nan")
    return out


def run_evaluation(
    model: str,
    dataset_name: str,
    prompt_version: str = "v1.0",
    seed: int | None = None,
    repeats: int = 1,
    subset: list[str] | None = None,
    experiment: str = DEFAULT_EXPERIMENT,
    phase: str = "preliminary",
    extra_tags: dict[str, str] | None = None,
    note: str = "",
) -> str:
    """Run one (model × dataset × prompt × seed) condition and log it to MLflow.

    `repeats` runs the WHOLE dataset `repeats` times inside the same MLflow
    run and stores all rows in per_example.jsonl with a `repeat_index`
    column. Treat repeats as a within-run consistency measurement; use
    separate `seed` values for a between-run reproducibility check.

    Returns the MLflow run_id so callers can chain analysis.
    """
    config = RunConfig(
        model=model,
        dataset_name=dataset_name,
        prompt_version=prompt_version,
        seed=seed,
        repeats=repeats,
        subset=subset,
        experiment=experiment,
        phase=phase,
        extra_tags=dict(extra_tags or {}),
        note=note,
    )

    items, ds_hash, ds_spec = load_dataset(dataset_name, subset)
    if not items:
        raise ValueError(f"Dataset '{dataset_name}' loaded zero items (subset filter?).")

    start_mlflow(experiment_name=experiment)
    # start_mlflow calls mlflow.openai.autolog, so every underlying Ollama
    # chat completion will be traced as a child span under this run.

    run_name = f"{model}__{dataset_name}__{prompt_version}__seed-{seed}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({
            "model_name": model,
            "model_digest": _model_digest(model),
            "ollama_version": _ollama_version(),
            "dataset_name": dataset_name,
            "dataset_hash": ds_hash,
            "dataset_description": ds_spec.description,
            "dataset_subset_size": len(items),
            "prompt_version": prompt_version,
            "prompt_hash": _prompt_hash(prompt_version),
            "seed": seed if seed is not None else "unset",
            "repeats": repeats,
            "git_sha": _git_sha() or "unknown",
            "python_version": platform.python_version(),
            "phase": phase,
            "note": note[:250],
        })
        mlflow.set_tags({
            "model": model,
            "dataset": dataset_name,
            "prompt_version": prompt_version,
            "phase": phase,
            "run_type": "model_comparison",
            **config.extra_tags,
            **ds_spec.tags,
        })

        all_rows: list[dict] = []
        raw_outputs_dir = Path(mlflow.get_artifact_uri().replace("file:///", "").replace("file://", ""))
        # mlflow.get_artifact_uri sometimes points at a URI we can't write
        # to directly on Windows — fall back to local tmp directory and
        # upload with log_artifact instead. Writing per-run outputs to a
        # tmp dir and uploading is the portable path.
        tmp_dir = Path(f".mlflow_run_tmp_{run.info.run_id}")
        tmp_dir.mkdir(exist_ok=True)

        try:
            for repeat_index in range(repeats):
                log.info(">>> model=%s dataset=%s repeat=%d/%d", model, dataset_name, repeat_index + 1, repeats)
                for item_index, item in enumerate(items):
                    log.info("    [%d/%d] example=%s", item_index + 1, len(items), item.id)
                    row, raw, _ = asyncio.run(_run_one_example(item, model))
                    row["repeat_index"] = repeat_index
                    row["model"] = model
                    row["dataset_name"] = dataset_name
                    row["dataset_hash"] = ds_hash
                    row["prompt_version"] = prompt_version
                    row["seed"] = seed
                    row["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
                    all_rows.append(row)

                    if raw is not None:
                        raw_path = tmp_dir / f"raw__{item.id}__r{repeat_index}.json"
                        raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

            # Per-example rows: both the JSONL artifact (long-term storage)
            # and the MLflow table (clickable in the UI).
            per_example_path = tmp_dir / "per_example.jsonl"
            with per_example_path.open("w", encoding="utf-8") as f:
                for row in all_rows:
                    f.write(json.dumps(row, default=str) + "\n")
            mlflow.log_artifact(str(per_example_path))

            df = pd.DataFrame(all_rows)
            # log_table serialises to JSON; keep a compact copy in the UI
            mlflow.log_table(df, artifact_file="per_example_table.json")

            # Raw assessments: one file per (example, repeat) so a judge
            # pass can read them without re-running the models.
            for raw_file in tmp_dir.glob("raw__*.json"):
                mlflow.log_artifact(str(raw_file), artifact_path="raw_outputs")

            metrics = _aggregate(all_rows)
            mlflow.log_metrics({k: v for k, v in metrics.items() if v == v})  # drop NaN

            log.info("Run %s complete. Aggregates: %s", run.info.run_id, metrics)
            return run.info.run_id
        finally:
            # Best-effort cleanup; failure here must not mask an eval failure.
            try:
                for p in tmp_dir.glob("*"):
                    p.unlink()
                tmp_dir.rmdir()
            except Exception:
                pass
