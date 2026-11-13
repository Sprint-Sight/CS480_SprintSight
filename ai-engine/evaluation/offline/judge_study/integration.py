"""Integration with the existing SprintSight pipelines (Part 11): judge independence data,
judge-score export for attach_judge_scores, LLM grounding, and trace scorers for
evaluation/online/run_judges.py.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import mlflow
import pandas as pd
from llmops.mlflow_config import configure_mlflow
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment

from evaluation.offline.judge_study.config import (
    DEFAULT_JUDGE_MODEL,
    RUBRIC_MAX,
    RUBRIC_MIN,
    _judge_call,
    configure_judge_endpoint,
)
from evaluation.offline.judge_study.frame import (
    JudgeRecord,
    _format_analysis,
    render_assessment_for_judge,
    render_bundle_for_judge,
    render_gold_for_judge,
    render_rubric_criteria,
)
from evaluation.offline.judge_study.records import gold_by_fixture
from evaluation.offline.judge_study.specs import JudgeMetricSpec, selected_specs

log = logging.getLogger(__name__)


# -- 11a. Hand-off to attach_judge_scores.py ---------------------------------

def export_judge_scores(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    run_id: str | None = None,
    score_column: str = "judge_composite",
) -> Path:
    """Write the CSV ``evaluation/offline/attach_judge_scores.py`` consumes.

    That script has been waiting for exactly five columns -- mlflow_run_id,
    example_id, repeat_index, judge_quality_score, judge_rationale -- and the
    model-comparison harness has been emitting ``judge_quality_score=None``
    placeholders for them since it was written. This closes that loop, which
    is what makes

        python -m evaluation.offline.cli analyze --pairwise-metric judge_quality_score

    produce real numbers instead of an empty column.

    ``judge_quality_score`` is rescaled from the 1-5 rubric to 0-10 so it
    shares an axis with the harness's ``overall_score`` column and the two can
    appear on one plot without a reader silently comparing different scales.
    The rationale concatenates every per-dimension justification, because a
    merged score with no retrievable reasoning is not auditable.
    """
    if score_column not in frame.columns:
        raise KeyError(
            f"'{score_column}' is not in the frame. Run the judge first, or pass "
            f"score_column= one of {[c for c in frame.columns if c.startswith('judge_')]}"
        )

    scores = pd.to_numeric(frame[score_column], errors="coerce")
    # 1-5 -> 0-10 linear rescale: (x - 1) / 4 * 10.
    rescaled = (scores - RUBRIC_MIN) / (RUBRIC_MAX - RUBRIC_MIN) * 10.0

    rationale_columns = [
        column for column in frame.columns if column.startswith("rationale_")
    ]

    def combine(row: pd.Series) -> str:
        parts = []
        for column in rationale_columns:
            value = row.get(column)
            if isinstance(value, str) and value.strip():
                parts.append(f"[{column.removeprefix('rationale_')}] {value.strip()}")
        return " | ".join(parts)

    run_ids = (
        [run_id] * len(frame)
        if run_id
        else (
            frame["mlflow_run_id"].tolist()
            if "mlflow_run_id" in frame.columns
            else [""] * len(frame)
        )
    )
    repeats = (
        frame["repeat_index"].tolist()
        if "repeat_index" in frame.columns
        else [0] * len(frame)
    )
    export = pd.DataFrame({
        "mlflow_run_id": run_ids,
        "example_id": frame["example_id"],
        "repeat_index": repeats,
        "judge_quality_score": rescaled,
        "judge_rationale": frame.apply(combine, axis=1) if rationale_columns else "",
    })
    # Carry the source scale so nobody has to reverse-engineer the rescale.
    export["judge_score_raw_1_5"] = scores
    export["judge_score_column"] = score_column

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    export.to_csv(destination, index=False)
    log.info(
        "Wrote %d judge scores to %s. Attach with: python -m "
        "evaluation.offline.attach_judge_scores --judge-file %s --run-id <run_id>",
        len(export), destination, destination,
    )
    return destination


# -- 11b. Optional LLM grounding column from the existing judge --------------

def attach_llm_grounding(
    frame: pd.DataFrame,
    records: Sequence[JudgeRecord],
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
) -> pd.DataFrame:
    """Add the existing citation-grounding judge's verdict as extra columns.

    ``evaluation/judges/citation_grounding.py`` already implements a careful
    per-claim grounding judge with a closure-validated response model that
    forces exactly one verdict per citation id. Rather than fold that
    behaviour into a rubric dimension and lose its per-claim resolution, its
    output is attached alongside: ``llm_hallucination_rate``,
    ``llm_grounded_rate`` and ``llm_judge_coverage``.

    The payoff is a three-way cross-check on the same claims -- deterministic
    anchors (citation_anchor_rate), deterministic string grounding
    (groundedness_rate, from summarise_example) and semantic grounding
    (these columns). Where the three disagree, the citation is worth a human
    look, and that disagreement is information no single metric provides.

    Skipped with a warning if that judge or its model is unavailable; this is
    an enrichment, not a dependency.
    """
    try:
        import asyncio

        from evaluation.judges.citation_grounding import judge_assessment
    except Exception:
        log.warning("citation_ground_custom_judge unavailable; skipping.", exc_info=True)
        return frame

    enriched = frame.copy()
    by_key = {(record.example_id, record.model, record.repeat_index): record for record in records}
    results: list[dict[str, Any]] = []

    for _, row in enriched.iterrows():
        record = by_key.get((row["example_id"], row["model"], row.get("repeat_index", 0)))
        if record is None or record.candidate is None:
            results.append({})
            continue
        try:
            verdict = asyncio.run(
                judge_assessment(record.bundle, record.candidate.rubric_scores, judge_model)
            )
            results.append({
                "llm_judge_coverage": verdict.get("coverage"),
                "llm_hallucination_rate": verdict.get("hallucination_rate"),
                "llm_grounded_rate": verdict.get("grounded_rate"),
                "llm_citation_count": verdict.get("citation_count"),
            })
        except Exception as error:  # noqa: BLE001
            log.warning(
                "LLM grounding judge failed for %s/%s: %s",
                row["model"], row["example_id"], error,
            )
            results.append({})

    for column in (
        "llm_judge_coverage",
        "llm_hallucination_rate",
        "llm_grounded_rate",
        "llm_citation_count",
    ):
        enriched[column] = [item.get(column) for item in results]
    return enriched


# -- 11c. Bridge to the trace-based pipeline in evaluation/online/ ------------

def build_trace_scorers(
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    metrics: Sequence[str] | None = None,
    bundle_by_team: Mapping[str, ArtifactBundle] | None = None,
    gold_by_team: Mapping[str, SprintAssessment] | None = None,
    cot_mode: Literal["two_stage", "inline"] = "two_stage",
) -> list[Any]:
    """Expose these rubrics as ``mlflow.genai.scorers`` for evaluation/online/run_judges.py.

    That pipeline judges logged TRACES, not stored assessment files, and it
    reads the candidate back with ``trace_adapters.read_candidate``. Rather
    than ask it to change, this returns scorers in the shape it already
    passes to ``mlflow.genai.evaluate(data=traces, scorers=[...])``:

        from evaluation.offline.judge_study import build_trace_scorers
        scorers = [grade_accuracy_from_trace, *build_trace_scorers()]

    The result is that the trace pipeline gains all five rubric dimensions
    with anchored 1-5 bands and the two-stage reasoning pass, while keeping
    its own citation-grounding judge and its numeric scorer -- and both
    pipelines are then scoring against the same rubric text, with the same
    rubric_hash, so their numbers are comparable.

    `bundle_by_team` / `gold_by_team` default to the benchmark fixtures; pass
    the CS203 maps when judging real sprints.
    """
    from mlflow.entities import AssessmentSource, AssessmentSourceType, Feedback, Trace
    from mlflow.genai.scorers import scorer
    from mlflow.metrics.genai.genai_metric import _extract_score_and_justification

    from evaluation.benchmarks.synthetic_v1 import FIXTURES
    from evaluation.judges.trace_adapters import read_candidate

    bundles = dict(bundle_by_team or {b.team_id: b for b in FIXTURES.values()})
    golds = dict(gold_by_team or {g.team_id: g for g in gold_by_fixture().values()})
    judge_uri = configure_judge_endpoint(judge_model)
    source = AssessmentSource(
        source_type=AssessmentSourceType.LLM_JUDGE, source_id=f"ollama:/{judge_model}"
    )

    def make_one(spec: JudgeMetricSpec) -> Any:
        @scorer(name=spec.name)
        def trace_scorer(trace: Trace) -> list[Feedback]:
            team = trace.info.tags.get("team_id") or ""
            bundle = bundles.get(team)
            gold = golds.get(team)
            if bundle is None or gold is None:
                return [Feedback(
                    name=spec.name,
                    value=None,
                    rationale=f"No bundle/gold registered for team_id={team!r}.",
                    source=source,
                )]
            try:
                # Same adapter, same citation filter, as the existing scorers.
                rubric, _dropped = read_candidate(trace, bundle)
                candidate = SprintAssessment(
                    sprint_id=bundle.sprint_id,
                    team_id=bundle.team_id,
                    prompt_version=trace.info.tags.get("prompt_version", "unknown"),
                    overall_score=(
                        sum(s.score for s in rubric.scored()) / len(rubric.scored())
                        if rubric.scored() else 0.0
                    ),
                    rubric_scores=rubric,
                    executive_summary="",
                    key_recommendations=[],
                )
                prediction = render_assessment_for_judge(candidate)
                context_values = {
                    "artifact_bundle": render_bundle_for_judge(bundle),
                    "gold_reference": render_gold_for_judge(gold),
                    "rubric_criteria": render_rubric_criteria(),
                }
                grading_context = {
                    column: context_values[column]
                    for column in spec.grading_context_columns
                    if column in context_values
                }
                if cot_mode == "two_stage":
                    audit = _format_analysis(
                        _judge_call(
                            spec.analysis_prompt(
                                prediction=prediction, grading_context=grading_context
                            ),
                            judge_uri,
                        )
                    )
                    grading_context[spec.cot_column()] = audit
                prompt = spec.eval_prompt_for(
                    judge_uri=judge_uri,
                    prediction=prediction,
                    inputs=f"Grade sprint {bundle.sprint_id} for team {bundle.team_id}.",
                    grading_context=grading_context,
                )
                score, justification = _extract_score_and_justification(
                    _judge_call(prompt, judge_uri)
                )
            except Exception as error:  # noqa: BLE001 - one bad call must not kill the run
                return [Feedback(name=spec.name, error=error, source=source)]
            return [Feedback(
                name=spec.name,
                value=score,
                rationale=justification,
                source=source,
                metadata={"rubric_hash": spec.rubric_hash(), "cot_mode": cot_mode},
            )]

        return trace_scorer

    return [make_one(spec) for spec in selected_specs(metrics)]


def load_records_from_traces(
    experiment_name: str,
    *,
    trace_ids: Sequence[str] | None = None,
    model: str | None = None,
    team_id: str | None = None,
    max_results: int = 50,
    bundle_by_team: Mapping[str, ArtifactBundle] | None = None,
    gold_by_team: Mapping[str, SprintAssessment] | None = None,
) -> list[JudgeRecord]:
    """Build JudgeRecords from logged traces, reusing evaluation/online/run_judges.py's
    own trace selection and candidate-reading logic.

    This is the other direction of the bridge in ``build_trace_scorers``: it
    lets the full statistical apparatus here -- calibration, position-swap
    debiasing, bootstrap CIs, the judge card -- run over traces produced by
    the live FastAPI service, not only over the research harness's stored
    assessment files.
    """
    from mlflow import MlflowClient

    from evaluation.benchmarks.synthetic_v1 import FIXTURES
    from evaluation.judges.trace_adapters import read_candidate

    # The same trace selection as evaluation/online/run_judges.py, so both pipelines
    # judge traces chosen by identical criteria.
    from evaluation.online.run_judges import select_traces

    configure_mlflow()
    bundles = dict(bundle_by_team or {b.team_id: b for b in FIXTURES.values()})
    golds = dict(gold_by_team or {g.team_id: g for g in gold_by_fixture().values()})

    client = MlflowClient()
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise KeyError(f"MLflow experiment '{experiment_name}' not found.")
    traces = select_traces(
        client,
        experiment.experiment_id,
        trace_ids=list(trace_ids) if trace_ids else None,
        model=model,
        team_id=team_id,
        max_results=max_results,
    )

    records: list[JudgeRecord] = []
    for trace in traces:
        team = trace.info.tags.get("team_id") or ""
        bundle, gold = bundles.get(team), golds.get(team)
        if bundle is None or gold is None:
            log.warning("Skipping trace %s: no bundle/gold for team_id=%r",
                        trace.info.trace_id, team)
            continue
        try:
            rubric, _ = read_candidate(trace, bundle)
            scored = rubric.scored()
            candidate = SprintAssessment(
                sprint_id=bundle.sprint_id,
                team_id=bundle.team_id,
                prompt_version=trace.info.tags.get("prompt_version", "unknown"),
                overall_score=(
                    sum(s.score for s in scored) / len(scored) if scored else 0.0
                ),
                rubric_scores=rubric,
                executive_summary="",
                key_recommendations=[],
            )
            error = None
        except Exception as exc:  # noqa: BLE001
            candidate, error = None, f"{type(exc).__name__}: {exc}"
        records.append(
            JudgeRecord(
                example_id=trace.info.trace_id,
                model=trace.info.tags.get("model")
                or trace.info.tags.get("model_name")
                or model
                or "unknown",
                bundle=bundle,
                gold=gold,
                candidate=candidate,
                error=error,
            )
        )
    log.info("Built %d records from %d traces.", len(records), len(traces))
    return records
