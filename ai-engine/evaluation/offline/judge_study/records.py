"""Record loading and the stub judge (Part 10): JudgeRecords from runner runs, human
annotations, and a deterministic stub so the pipeline runs without a model server.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment

from evaluation.offline.judge_study.config import RUBRIC_MAX, RUBRIC_MIN
from evaluation.offline.judge_study.deterministic import _GENERIC_FILLER, _HARD_ANCHOR
from evaluation.offline.judge_study.frame import JudgeRecord
from evaluation.offline.judge_study.specs import JUDGE_METRIC_NAMES

log = logging.getLogger(__name__)


def gold_by_fixture() -> dict[str, SprintAssessment]:
    """Map each benchmark fixture key to its human-authored gold assessment."""
    from evaluation.benchmarks import synthetic_v1 as benchmark

    return {
        "high_performing": benchmark.high_performing_grade,
        "struggling": benchmark.struggling_grade,
        "good_collab_low_output": benchmark.good_collab_low_output_grade,
        "imbalanced_high_output": benchmark.imbalanced_high_output_grade,
        "lone_contributor_poor_outcome": benchmark.lone_contributor_poor_outcome_grade,
    }


def bundles_for_run(params: Mapping[str, str]) -> dict[str, ArtifactBundle]:
    """The bundles a runner run graded, keyed by example id, from the dataset it logged.

    Runs logged before the dataset name was recorded fall back to the synthetic fixtures. A
    dataset whose hash no longer matches the run (re-exported since) is still used, with a
    warning: the judge would then read different evidence from what the candidate was graded on.
    """
    from evaluation.benchmarks.synthetic_v1 import FIXTURES
    from evaluation.offline.datasets import load_dataset

    name = params.get("dataset_name")
    if not name:
        return dict(FIXTURES)
    items, digest, _ = load_dataset(name)  # nosec B615
    logged = params.get("dataset_hash")
    if logged and logged != digest:
        log.warning(
            "Dataset %s has changed since this run (hash %s, run logged %s); the judge will read "
            "the current bundles.", name, digest, logged,
        )
    return {item.id: item.bundle for item in items}


def load_records_from_run(
    run_id: str,
    *,
    model: str | None = None,
    human_annotations: str | Path | None = None,
) -> list[JudgeRecord]:
    """Rebuild JudgeRecords from a `evaluation.offline.runner` MLflow run.

    The runner already logs each candidate SprintAssessment to
    `raw_outputs/raw__<example>__r<n>.json`, so judging reads from MLflow
    rather than re-running the candidate models. That matters for more than
    cost: it guarantees the judged artifact is byte-identical to the one the
    deterministic metrics in that run were computed on.
    """
    client = mlflow.tracking.MlflowClient()
    run = client.get_run(run_id)
    resolved_model = model or run.data.params.get("model_name") or "unknown"
    bundles = bundles_for_run(run.data.params)
    golds = gold_by_fixture()  # the synthetic fixtures only; real sprints have none

    destination = Path(".eval_cache") / run_id
    destination.mkdir(parents=True, exist_ok=True)

    records: list[JudgeRecord] = []
    for artifact in client.list_artifacts(run_id, "raw_outputs"):
        if not artifact.path.endswith(".json"):
            continue
        local = Path(client.download_artifacts(run_id, artifact.path, str(destination)))
        stem = local.stem  # raw__<example>__r<n>
        parts = stem.split("__")
        if len(parts) < 3:
            log.warning("Unexpected raw output filename %s; skipping.", local.name)
            continue
        example_id = parts[1]
        repeat_index = int(parts[2].lstrip("r") or 0)
        if example_id not in bundles:
            log.warning("No bundle for example '%s' in the run's dataset; skipping.", example_id)
            continue
        raw = json.loads(local.read_text(encoding="utf-8"))
        try:
            candidate = SprintAssessment(**raw)
            error = None
        except Exception as exc:  # noqa: BLE001 - a malformed output is data
            candidate, error = None, f"{type(exc).__name__}: {exc}"
        records.append(
            JudgeRecord(
                example_id=example_id,
                model=resolved_model,
                bundle=bundles[example_id],
                gold=golds.get(example_id),
                candidate=candidate,
                candidate_raw=raw,
                error=error,
                repeat_index=repeat_index,
            )
        )

    if human_annotations:
        attach_human_annotations(records, human_annotations)
    log.info("Loaded %d records from run %s.", len(records), run_id)
    return records


def attach_human_annotations(
    records: Sequence[JudgeRecord], path: str | Path
) -> int:
    """Attach human baseline scores from a CSV, returning the number matched.

    Expected columns: ``example_id``, ``model``, and one column per judge
    metric holding that annotator's 1-5 score. Unmatched annotation rows are
    logged rather than silently dropped -- a typo in a model name that
    quietly halves the calibration sample is exactly the kind of error that
    makes a kappa unreproducible.
    """
    table = pd.read_csv(path)
    required = {"example_id", "model"}
    if not required.issubset(table.columns):
        raise ValueError(f"Annotation file must contain columns {sorted(required)}")

    index: dict[tuple[str, str], dict[str, float]] = {}
    for _, row in table.iterrows():
        scores = {
            name: float(row[name])
            for name in JUDGE_METRIC_NAMES
            if name in table.columns and pd.notna(row[name])
        }
        if scores:
            index[(str(row["example_id"]), str(row["model"]))] = scores

    matched = 0
    for record in records:
        scores = index.pop((record.example_id, record.model), {})
        if scores:
            record.human_scores = scores
            matched += 1
    if index:
        log.warning(
            "%d annotation row(s) matched no record and were ignored: %s",
            len(index),
            sorted(index)[:5],
        )
    log.info("Attached human annotations to %d of %d records.", matched, len(records))
    return matched


# -- Stub judge ---------------------------------------------------------------

_STUB_ORIGINAL: Any = None


def install_stub_judge(*, noise: float = 0.0, seed: int = 0) -> None:
    """Replace the judge transport with a deterministic, content-sensitive stub.

    Purpose is CI, not simulation. The whole pipeline -- prompt rendering,
    MLflow metric wiring, score parsing, calibration arithmetic, figures,
    artifact logging -- can then be exercised on a laptop with no model
    server, which is what makes the framework itself testable rather than
    only its outputs inspectable.

    The stub reads the rendered prompt and scores on hard-anchor density and
    filler presence, so it is correlated with quality rather than random:
    a constant stub would make every agreement coefficient trivially zero
    and hide wiring bugs in the calibration code.
    """
    global _STUB_ORIGINAL
    from mlflow.metrics.genai import model_utils

    if _STUB_ORIGINAL is None:
        _STUB_ORIGINAL = model_utils.score_model_on_payload

    rng = random.Random(seed)

    def stub(model_uri: str, payload: str, *args: Any, **kwargs: Any) -> str:
        if not payload or not payload.strip():
            raise AssertionError(
                "The judge was handed an EMPTY prompt -- this is the "
                "PromptTemplate brace failure described in the module docstring."
            )

        if "ASSESSMENT A:" in payload and "ASSESSMENT B:" in payload:
            section_a = payload.split("ASSESSMENT A:", 1)[1].split("ASSESSMENT B:", 1)[0]
            section_b = payload.split("ASSESSMENT B:", 1)[1]
            score_a = len(_HARD_ANCHOR.findall(section_a))
            score_b = len(_HARD_ANCHOR.findall(section_b))
            winner = "A" if score_a > score_b else "B" if score_b > score_a else "TIE"
            return json.dumps({
                "comparison": f"A cites {score_a} anchors, B cites {score_b}.",
                "decisive_criterion": "specificity",
                "winner": winner,
            })

        output = payload.split("Output:", 1)[-1].split("Metric definition:", 1)[0]
        anchors = len(_HARD_ANCHOR.findall(output))
        filler = sum(phrase in output.lower() for phrase in _GENERIC_FILLER)
        failed = "NO USABLE ASSESSMENT" in output or "EVALUATION FAILED" in output

        if failed:
            score = 1
        else:
            score = 1 + min(4, anchors // 3) - min(2, filler)
            score = max(RUBRIC_MIN, min(RUBRIC_MAX, score))
        if noise:
            score = int(max(RUBRIC_MIN, min(RUBRIC_MAX, round(score + rng.gauss(0, noise)))))

        return json.dumps({
            "evidence_scan": [f"counted {anchors} hard anchors", f"counted {filler} filler phrases"],
            "anchor_check": f"T1 {'PASSED' if anchors else 'FAILED'}; T2 stub does not verify",
            "justification": (
                f"Stub judge: {anchors} hard anchors and {filler} filler phrases "
                f"place this output in band {score}."
            ),
            "score": score,
        })

    model_utils.score_model_on_payload = stub
    log.warning("STUB JUDGE INSTALLED -- scores are synthetic and must not be reported.")


def uninstall_stub_judge() -> None:
    global _STUB_ORIGINAL
    if _STUB_ORIGINAL is not None:
        from mlflow.metrics.genai import model_utils

        model_utils.score_model_on_payload = _STUB_ORIGINAL
        _STUB_ORIGINAL = None


def synthetic_records(
    *, degrade: bool = True, with_human_annotations: bool = True
) -> list[JudgeRecord]:
    """Pipeline-validation dataset built from the benchmark fixtures.

    NOT a result and never reportable. Two simulated candidates are derived
    from the gold assessments -- one faithful copy and one deliberately
    degraded (citations stripped, recommendations replaced with filler,
    scores inflated) -- so the framework can be checked end to end for the
    property that actually matters: that the degraded model scores WORSE.
    A pipeline that cannot reproduce a known ordering on data where the
    answer is known should not be trusted on data where it is not.

    The accompanying "human" annotations are derived from the known
    construction, not collected from people. They validate the calibration
    arithmetic; they are not evidence about the judge.
    """
    import copy

    from evaluation.benchmarks.synthetic_v1 import FIXTURES

    golds = gold_by_fixture()
    records: list[JudgeRecord] = []

    for example_id, bundle in FIXTURES.items():
        gold = golds[example_id]

        faithful = copy.deepcopy(gold)
        faithful.prompt_version = "synthetic-faithful"
        records.append(
            JudgeRecord(
                example_id=example_id,
                model="synthetic-faithful",
                bundle=bundle,
                gold=gold,
                candidate=faithful,
                human_scores=(
                    {name: 5.0 for name in JUDGE_METRIC_NAMES}
                    if with_human_annotations else None
                ),
                latency_s=12.0,
            )
        )

        if not degrade:
            continue

        degraded = copy.deepcopy(gold)
        degraded.prompt_version = "synthetic-degraded"
        degraded.key_recommendations = [
            "Keep up the good work and continue to improve going forward.",
            "Improve communication across the team.",
        ]
        for dimension in DIMENSIONS:
            score = getattr(degraded.rubric_scores, dimension, None)
            if score is None:
                continue
            score.evidence_citations = []
            score.justification = "The team generally did well overall."
            # Inflate by two, clipped to the schema's 1-10 bound.
            score.score = min(10, score.score + 2)
        degraded.overall_score = min(10.0, float(gold.overall_score) + 2.0)
        records.append(
            JudgeRecord(
                example_id=example_id,
                model="synthetic-degraded",
                bundle=bundle,
                gold=gold,
                candidate=degraded,
                human_scores=(
                    {name: 1.0 for name in JUDGE_METRIC_NAMES}
                    if with_human_annotations else None
                ),
                latency_s=9.0,
            )
        )

    return records
