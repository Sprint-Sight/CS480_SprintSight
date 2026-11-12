"""The hybrid eval frame and mlflow.evaluate() orchestration (Part 4): rendering records for
the judge, building the frame, the deterministic metrics and the two-stage judge run.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import Parameter, Signature
from typing import Any, Literal

import mlflow
import pandas as pd
from mlflow.metrics import make_metric
from mlflow.metrics.base import MetricValue

from evaluation.offline.judge_study.artifacts import _log_run_artifacts
from evaluation.offline.judge_study.config import (
    DEFAULT_JUDGE_MODEL,
    JUDGE_BUNDLE_CHAR_BUDGET,
    JUDGE_EXPERIMENT,
    JUDGE_MAX_TOKENS,
    JUDGE_SEED,
    RUBRIC_MAX,
    RUBRIC_MIN,
    _judge_call,
    _strip_braces,
    assert_judge_independence,
    configure_judge_endpoint,
)
from evaluation.offline.judge_study.deterministic import (
    citation_anchor_metrics,
    lint_assessment,
    numeric_grade_errors,
    python_snippet_syntax_valid,
    rouge_l_f1,
    schema_round_trip_ok,
    token_overlap_f1,
)
from evaluation.offline.judge_study.specs import (
    GOLD_DEPENDENT_METRICS,
    GOLD_FREE_METRICS,
    JUDGE_METRIC_NAMES,
    JUDGE_METRIC_SPECS,
    JudgeMetricSpec,
    build_genai_metrics,
    selected_specs,
)
from evaluation.offline.metrics import summarise_example
from evaluation.offline.provenance import git_sha, model_digest
from llmops.mlflow_config import configure_mlflow, get_experiment_id
from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment

log = logging.getLogger(__name__)


#
# One pandas DataFrame carries both metric families into a single
# ``mlflow.evaluate`` call, so the LLM judgements and the deterministic
# checks land in the same run, against the same rows, with the same
# provenance. Splitting them across two runs is how eval pipelines end up
# comparing a judge score from Tuesday against a groundedness rate from
# Thursday's dataset.

# -- 4a. Rendering: prose, not JSON ------------------------------------------
#
# The judge is shown prose, not the raw SprintAssessment JSON. Three reasons:
# a local 3B-8B model spends a large share of attention on JSON punctuation;
# brace characters are hazardous anywhere near MLflow's PromptTemplate (Part
# 0); and the few-shot exemplars are prose, so a JSON payload at inference
# time would be off-distribution from the calibration examples.


def render_assessment_for_judge(assessment: SprintAssessment | None, error: str | None = None) -> str:
    """Flatten a SprintAssessment into brace-free prose for the judge."""
    if assessment is None:
        return _strip_braces(
            "THE CANDIDATE MODEL PRODUCED NO USABLE ASSESSMENT. "
            f"Failure: {error or 'unknown error'}."
        )

    lines = [
        (f"Team {assessment.team_id}, sprint {assessment.sprint_id}, "
        f"graded by prompt version {assessment.prompt_version}."),
        f"Overall score: {assessment.overall_score} out of 10.",
        "",
        "Per-dimension assessment:",
    ]
    for dimension in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dimension, None)
        if score is None:
            lines.append(f"- {dimension}: NOT PRODUCED by the model.")
            continue
        if score.evaluation_failed:
            lines.append(f"- {dimension}: EVALUATION FAILED, placeholder only.")
            continue
        lines.append(f"- {dimension}: scored {score.score} out of 10.")
        lines.append(f"  Justification: {score.justification}")
        if score.evidence_citations:
            for citation in score.evidence_citations:
                lines.append(f"  Evidence: {citation.identifier} -- {citation.reason}")
        else:
            lines.append("  Evidence: none cited.")

    if assessment.executive_summary:
        lines += ["", f"Executive summary: {assessment.executive_summary}"]
    if assessment.strengths:
        lines += ["", "Strengths:"] + [f"- {item}" for item in assessment.strengths]
    if assessment.weaknesses:
        lines += ["", "Weaknesses:"] + [f"- {item}" for item in assessment.weaknesses]
    lines += ["", "Key recommendations:"] + [
        f"- {item}" for item in (assessment.key_recommendations or ["none given"])
    ]
    return _strip_braces("\n".join(lines))


def candidate_visible_commits(bundle: ArtifactBundle) -> list[dict[str, Any]]:
    """The commits the candidate model could legitimately have cited.

    This reuses ``services.llm_client``'s own sampling rather than the raw
    commit list, because the two are wildly different on a real sprint. The
    candidate never sees every commit: ``evaluate_dimension`` trims noise
    files, then takes ``_COMMIT_BUDGET`` representative commits PER DIMENSION
    (by file pattern, recency and churn). So the set of citable commits is the
    UNION of those per-dimension samples -- 64 to 89 commits on the real
    sprints, not the 223 to 544 the bundle contains.

    Showing the judge anything else breaks faithfulness judging outright.
    Measured before this function existed: the judge was shown the first ~20
    commits in bundle order, of which 1 to 3 overlapped with the 30 the
    candidate was given, so 27 to 29 of every 30 legitimately citable commits
    were invisible and would have been scored as fabrications.

    The private imports are deliberate. Re-deriving this sampling here is
    precisely the bug: the judge's view must change in lockstep with the
    candidate's, so it has to be the same code. If llm_client ever makes
    these public, drop the underscores and nothing else changes.
    """
    from services.llm_client import (
        _COMMIT_BUDGET,
        _DIMENSION_ARTIFACT_FIELDS,
        _select_representative_commits,
        _trim_commits,
    )

    trimmed = _trim_commits(bundle.model_dump(mode="json")["commits"])
    citable: dict[str, dict[str, Any]] = {}
    for dimension in DIMENSIONS:
        if "commits" not in _DIMENSION_ARTIFACT_FIELDS.get(dimension, ()):
            continue
        for commit in _select_representative_commits(trimmed, dimension, _COMMIT_BUDGET):
            citable.setdefault(commit["sha"], commit)
    # Chronological so the judge reads a sprint narrative rather than an
    # arbitrary sampling order.
    return sorted(citable.values(), key=lambda commit: str(commit.get("timestamp") or ""))


def render_bundle_for_judge(
    bundle: ArtifactBundle, char_budget: int = JUDGE_BUNDLE_CHAR_BUDGET
) -> str:
    """Render the candidate's own evidence view as brace-free prose.

    Three things the judge is given, matching what the candidate had:

      1. The citable commits (see ``candidate_visible_commits``), with the
         same trimmed file lists the candidate saw -- so a filename citation
         is verifiable, and a filename the candidate never saw is not
         presented as if it were.
      2. ``_compute_commit_facts`` / ``_compute_jira_facts``: the precomputed
         aggregates the candidate's prompt tells it to "trust over your own
         counting". Without these the judge cannot check a claim like "223
         commits by 10 authors", because it is only shown a sample, and would
         score a correct aggregate as unverifiable.
      3. Tickets, peer evaluations and metrics in full -- these are small
         (around 11 tickets even on the real sprints) and are never sampled.

    Any truncation drops whole commits from the end and says how many, rather
    than cutting mid-record: half a commit is worse than no commit, because
    its SHA may survive while its author does not.
    """
    from services.llm_client import (
        _COMMIT_BUDGET,
        _compute_commit_facts,
        _compute_jira_facts,
        _trim_commits,
    )

    raw = bundle.model_dump(mode="json")
    trimmed = _trim_commits(raw["commits"])
    commits = candidate_visible_commits(bundle)
    withheld = len(trimmed) - len(commits)

    header = [
        f"Team {bundle.team_id}, sprint {bundle.sprint_id}.",
        "",
        (
            f"EVIDENCE SCOPE: the sprint contains {len(trimmed)} commits. The "
            f"{len(commits)} listed below are exactly the ones the candidate "
            "model was shown and could cite. The aggregate figures further "
            "down are computed over ALL commits and the candidate was given "
            "them too, so a claim about sprint-wide totals is checkable "
            "against those."
        ),
    ]
    if withheld > 0:
        header.append(
            f"The other {withheld} commits were NOT shown to the candidate "
            "either, so it had no way to copy their identifiers from the "
            "evidence."
        )

    def commit_line(commit: dict[str, Any], file_cap: int | None) -> str:
        """One commit. ``file_cap`` None shows every file, 0 shows none."""
        changed = commit.get("files_changed") or []
        core = (
            f"- {commit['sha']} by {commit.get('author')} at "
            f"{commit.get('timestamp')}: {commit.get('message')} (plus "
            f"{commit.get('lines_added', 0)}, minus {commit.get('lines_deleted', 0)}"
        )
        if file_cap == 0:
            return core + f"; {len(changed)} file(s) changed, names not shown)"
        if not changed:
            return core + "; no files recorded)"
        if file_cap is None or len(changed) <= file_cap:
            return core + f"; files: {', '.join(changed)})"
        remainder = len(changed) - file_cap
        return (
            core
            + f"; files: {', '.join(changed[:file_cap])} and {remainder} more files)"
        )

    tail: list[str] = ["", "Jira tickets:"]
    for ticket in bundle.jira_tickets:
        points = "not estimated" if ticket.story_points is None else f"{ticket.story_points:g}"
        tail.append(
            f"- {ticket.ticket_id} {ticket.summary}: status {ticket.status}, "
            f"type {ticket.issue_type}, assignee {ticket.assignee or 'unassigned'}, "
            f"story points {points}"
        )
    if not bundle.jira_tickets:
        tail.append("- none")

    tail += ["", "Peer evaluations:"]
    for evaluation in bundle.peer_evaluations:
        tail.append(
            f"- {evaluation.evaluator} rated {evaluation.evaluatee} "
            f"{evaluation.rating} out of 5: {evaluation.comments}"
        )
    if not bundle.peer_evaluations:
        tail.append("- none")

    facts = "\n\n".join(
        section
        for section in (
            _compute_commit_facts(trimmed, _COMMIT_BUDGET),
            _compute_jira_facts(raw["jira_tickets"]),
        )
        if section
    )
    if facts:
        tail += ["", "Precomputed aggregates over ALL commits and tickets:", facts]

    tail += [
        "",
        f"Artifact metrics: {bundle.artifact_metrics or 'none recorded'}",
        f"Collaboration metrics: {bundle.collaboration_metrics or 'none recorded'}",
        f"Instructor expectations: {bundle.instructor_expectations}",
    ]

    # Degrade file DETAIL before dropping any commit. Priority order is
    # deliberate: a commit SHA is the primary citation anchor and is short, so
    # every SHA must stay verifiable even on a 544-commit sprint. A file list
    # is long and secondary, so when the budget bites, file citations degrade
    # to "unverifiable" (which the judge is told to record as unresolved)
    # rather than SHA citations degrading to "fabricated". Full file lists
    # render at 45-49k chars on the real sprints; the SHAs alone are 11-13k.
    fixed = _strip_braces("\n".join([*header, "", "Commits the candidate was shown:", *tail]))
    available = char_budget - len(fixed)

    file_cap: int | None = None
    shown: list[str] = []
    for candidate_cap in (None, 8, 4, 2, 0):
        lines = [_strip_braces(commit_line(commit, candidate_cap)) for commit in commits]
        if sum(len(line) + 1 for line in lines) <= available:
            file_cap, shown = candidate_cap, lines
            break
        file_cap, shown = candidate_cap, lines

    # Last resort: even SHA-only lines do not fit, so drop whole commits.
    dropped = 0
    while shown and sum(len(line) + 1 for line in shown) > available:
        shown.pop()
        dropped += 1

    notes: list[str] = []
    if file_cap == 0:
        notes.append(
            "[File lists are omitted for every commit to fit the prompt budget. "
            "A filename citation therefore cannot be confirmed or denied here: "
            "record it under unresolved, never as fabricated. Commit SHAs, "
            "authors, dates, messages and line counts above are complete.]"
        )
    elif file_cap is not None:
        notes.append(
            f"[Only the first {file_cap} changed files are listed per commit, to "
            "fit the prompt budget. A commit showing 'and N more files' may well "
            "contain a cited file that is not printed: record such a citation "
            "under unresolved, never as fabricated.]"
        )
    if dropped:
        notes.append(
            f"[{dropped} of the {len(commits)} citable commits did not fit and "
            "are NOT shown. Do not treat a citation as fabricated merely "
            "because you cannot find it here; record it under unresolved.]"
        )

    body = [*header, "", "Commits the candidate was shown:", *(shown or ["- none"]), *notes]
    return _strip_braces("\n".join([*body, *tail]))


def render_rubric_criteria() -> str:
    """The live rubric text, so Rubric_Adherence is judged against the same
    criteria the candidate was graded with rather than the judge's taste."""
    return _strip_braces(
        "\n\n".join(
            f"Dimension {dimension}:\n{DIMENSION_PROMPTS[dimension]}"
            for dimension in DIMENSIONS
        )
    )


NO_GOLD_REFERENCE = (
    "No human reference assessment exists for this sprint. Judge against the artifacts only."
)


def render_gold_for_judge(gold: SprintAssessment | None) -> str:
    """Compact gold reference: scores and bottleneck ordering only.

    Deliberately NOT the full gold narrative. Showing the judge a complete
    human-written assessment invites it to score candidates on textual
    similarity to gold rather than on the rubric, which would make
    Bug_Actionability a paraphrase detector.

    No gold (a real sprint) renders a neutral line, never placeholder scores.
    """
    if gold is None:
        return NO_GOLD_REFERENCE
    scores = []
    for dimension in DIMENSIONS:
        score = getattr(gold.rubric_scores, dimension, None)
        if score is not None:
            scores.append((dimension, float(score.score)))
    ordered = sorted(scores, key=lambda pair: pair[1])
    lines = [
        f"Human reference overall score: {gold.overall_score} out of 10.",
        "Human reference per-dimension scores out of 10: "
        + ", ".join(f"{name} {value:g}" for name, value in scores),
    ]
    if ordered:
        lines.append(
            "Lowest-scoring dimensions, weakest first: "
            + ", ".join(name for name, _ in ordered[:2])
        )
        lines.append(
            "Highest-scoring dimensions: "
            + ", ".join(name for name, _ in reversed(ordered[-2:]))
        )
    return _strip_braces("\n".join(lines))


# -- 4b. The record and the frame --------------------------------------------

@dataclass
class JudgeRecord:
    """One (candidate model, example) observation to be evaluated.

    ``human_scores`` is the meta-evaluation input: a mapping of judge metric
    name to the score a human annotator gave the SAME output on the SAME
    1-5 rubric. Left None for rows nobody has annotated; Part 5 computes
    agreement over whatever subset exists and reports its n, so a partially
    annotated dataset is usable without pretending to full coverage.
    """

    example_id: str
    model: str
    bundle: ArtifactBundle
    gold: SprintAssessment | None  # None for a real sprint: no human reference exists
    candidate: SprintAssessment | None = None
    candidate_raw: Mapping[str, Any] | None = None
    error: str | None = None
    human_scores: Mapping[str, float] | None = None
    latency_s: float | None = None
    repeat_index: int = 0

    def __post_init__(self) -> None:
        if self.candidate_raw is None and self.candidate is not None:
            self.candidate_raw = self.candidate.model_dump(mode="json")


def build_eval_frame(records: Sequence[JudgeRecord]) -> pd.DataFrame:
    """Assemble the single DataFrame that ``mlflow.evaluate`` consumes.

    Layered deliberately on top of ``evaluation.offline.metrics.summarise_example``
    rather than recomputing what the model-comparison harness already
    computes. Every column that harness emits into ``per_example.jsonl`` is
    present here under the same name and with the same definition, so:

      * a judge run and a ``runner.run_evaluation`` run are directly
        comparable without a column translation table;
      * ``groundedness_rate``, ``format_valid`` and
        ``dimension_completion_rate`` have exactly ONE definition in the
        codebase, and changing it changes both pipelines together;
      * the ``judge_quality_score`` / ``judge_rationale`` placeholder columns
        that ``summarise_example`` leaves for the judge arrive pre-created,
        which is precisely the hand-off ``attach_judge_scores.py`` expects.

    Columns this module ADDS on top of that base:
      inputs             the task statement (GenAI metrics need an `inputs` column)
      prediction         candidate assessment as prose  -> `predictions=`
      target             gold assessment as prose       -> `targets=`
      artifact_bundle    grading context (ground truth)
      gold_reference     grading context (scores only)
      rubric_criteria    grading context (live rubric text)
      citation_anchor_*  evidence SPECIFICITY (groundedness stays in the base)
      lint_warning_count rule-based defects
      rouge_l_vs_gold    leakage check against the gold narrative
      schema_valid       Pydantic re-validation of the raw output
      grade_*            delegated to evaluation.judges.grade_accuracy
      human_<metric>     optional human annotations for Part 5
    """
    if not records:
        raise ValueError("build_eval_frame received no records.")

    rubric_criteria = render_rubric_criteria()
    rows: list[dict[str, Any]] = []

    for record in records:
        candidate = record.candidate
        prediction = render_assessment_for_judge(candidate, record.error)
        target = render_assessment_for_judge(record.gold) if record.gold is not None else ""

        # Layer 1: the model-comparison harness's own per-example row, verbatim.
        row: dict[str, Any] = dict(
            summarise_example(record.bundle, candidate, record.error)
        )
        # summarise_example returns this as a list; mlflow.evaluate infers a
        # schema from the frame and chokes on list-valued columns.
        row["failed_dimension_names"] = json.dumps(row.get("failed_dimension_names") or [])

        # Layer 2: judge inputs and the checks that are new here.
        row.update({
            "example_id": record.example_id,
            "model": record.model,
            "repeat_index": record.repeat_index,
            "inputs": (
                f"Grade sprint {record.bundle.sprint_id} for team "
                f"{record.bundle.team_id} against the six-dimension SprintSight "
                f"rubric, citing only the supplied artifacts."
            ),
            "prediction": prediction,
            "target": target,
            "artifact_bundle": render_bundle_for_judge(record.bundle),
            "gold_reference": render_gold_for_judge(record.gold),
            "rubric_criteria": rubric_criteria,
            "schema_valid": schema_round_trip_ok(record.candidate_raw),
            "python_syntax_valid": python_snippet_syntax_valid(prediction),
            "rouge_l_vs_gold": rouge_l_f1(prediction, target) if target else None,
            "token_overlap_vs_gold": token_overlap_f1(prediction, target) if target else None,
            "latency_s": record.latency_s,
            "gold_overall_score": (
                float(record.gold.overall_score) if record.gold is not None else None
            ),
        })

        if candidate is not None:
            row.update(citation_anchor_metrics(record.bundle, candidate))
            lint = lint_assessment(candidate)
            row["lint_warning_count"] = float(lint["lint_warning_count"])
            row["lint_warnings"] = json.dumps(lint["lint_warnings"])
        else:
            row.update({
                "citation_anchor_rate": None,
                "dimension_anchor_coverage": None,
                # A total structural failure is the worst possible lint result,
                # not a missing one: leaving it None would let a model that
                # crashed drop out of the mean entirely and look better than a
                # model that produced something mediocre.
                "lint_warning_count": float(len(DIMENSIONS) + 1),
                "lint_warnings": json.dumps(["no_assessment_produced"]),
            })

        row.update(numeric_grade_errors(candidate, record.gold))

        for metric_name in JUDGE_METRIC_NAMES:
            human_value = (record.human_scores or {}).get(metric_name)
            row[f"human_{metric_name}"] = (
                float(human_value) if human_value is not None else None
            )

        rows.append(row)

    frame = pd.DataFrame(rows)
    log.info(
        "Eval frame: %d rows, %d models, %d examples, %d human-annotated rows",
        len(frame),
        frame["model"].nunique(),
        frame["example_id"].nunique(),
        int(frame[[f"human_{name}" for name in JUDGE_METRIC_NAMES]].notna().any(axis=1).sum()),
    )
    return frame


# -- 4c. Deterministic columns as first-class MLflow metrics ------------------
#
# MLflow binds a custom metric's eval_fn parameters to DataFrame columns BY
# PARAMETER NAME. We therefore need a function whose parameter is literally
# named after the column -- which means synthesising the signature, since the
# column names are data. `__signature__` is what `inspect.signature` reads,
# so setting it is sufficient and avoids generating code with exec.

DeterministicAggregate = Literal["mean", "sum", "rate"]


def _column_metric(
    column: str,
    *,
    name: str | None = None,
    greater_is_better: bool = True,
    aggregate: DeterministicAggregate = "mean",
) -> Any:
    """Promote a precomputed DataFrame column to an MLflow metric.

    Per-row values are already exact and reproducible, so the metric's only
    job is aggregation plus carrying the per-row scores into the MLflow eval
    table. Rows whose value is None are dropped from the aggregate and
    counted in ``n``, so a reader can always see what the mean was taken over
    -- the distinction that makes a "groundedness 1.0" over two rows honest.
    """

    def eval_fn(series: pd.Series) -> MetricValue:
        numeric = pd.to_numeric(pd.Series(series), errors="coerce")
        usable = numeric.dropna()
        if usable.empty:
            return MetricValue(
                scores=numeric.tolist(),
                aggregate_results={"n": 0.0},
            )
        if aggregate == "sum":
            point = float(usable.sum())
        else:
            point = float(usable.mean())
        results = {
            aggregate if aggregate != "rate" else "mean": point,
            "n": float(usable.shape[0]),
            "n_missing": float(numeric.isna().sum()),
        }
        if len(usable) >= 2:
            results["std"] = float(usable.std(ddof=1))
        return MetricValue(scores=numeric.tolist(), aggregate_results=results)

    eval_fn.__signature__ = Signature(  # type: ignore[attr-defined]
        [Parameter(column, Parameter.POSITIONAL_OR_KEYWORD, annotation="pd.Series")]
    )
    eval_fn.__name__ = f"eval_{column}"
    return make_metric(
        eval_fn=eval_fn,
        greater_is_better=greater_is_better,
        name=name or column,
    )


# (column, greater_is_better) for every deterministic check that should appear
# as an MLflow metric. Direction is declared explicitly so the MLflow UI and
# the comparison report in Part 8 both know which way is better -- a detail
# that silently inverts conclusions when left to a default.
DETERMINISTIC_METRIC_COLUMNS: tuple[tuple[str, bool], ...] = (
    # --- inherited verbatim from evaluation.offline.metrics.summarise_example ---
    ("format_valid", True),
    ("groundedness_rate", True),
    ("dimension_completion_rate", True),
    ("dimensions_present", True),
    # --- added by this module ---
    ("schema_valid", True),
    ("citation_anchor_rate", True),
    ("dimension_anchor_coverage", True),
    ("lint_warning_count", False),
    ("python_syntax_valid", True),
    ("rouge_l_vs_gold", True),
    ("token_overlap_vs_gold", True),
    # --- delegated to evaluation.judges.grade_accuracy.numeric_grade_accuracy ---
    ("grade_mae_per_dimension", False),
    ("grade_abs_error_overall", False),
    # Signed error is "greater is better" only in the sense that the MLflow UI
    # needs a direction; what matters is distance from zero in either
    # direction, which the judge card spells out.
    ("grade_signed_error_overall", True),
    ("latency_s", False),
)


def build_deterministic_metrics(frame: pd.DataFrame) -> list[Any]:
    """Metrics for whichever deterministic columns the frame actually has.

    Skipping absent columns rather than failing matters: MLflow raises on a
    metric whose parameter does not match a column, and a frame built from
    records with no latency recorded is still a perfectly valid frame.
    """
    metrics = []
    for column, greater_is_better in DETERMINISTIC_METRIC_COLUMNS:
        if column not in frame.columns:
            continue
        if pd.to_numeric(frame[column], errors="coerce").notna().sum() == 0:
            log.info("Skipping deterministic metric '%s': no usable values.", column)
            continue
        metrics.append(_column_metric(column, greater_is_better=greater_is_better))
    return metrics


def register_judge_prompts(alias: str = "production") -> dict[str, str]:
    """Version every judge rubric in the MLflow Prompt Registry.

    Best-effort by design: the registry is for provenance, and a tracking
    server being down must not stop a measurement run. Returns the rubric
    hashes either way, so the run is self-describing even with no registry.
    """
    hashes = {spec.name: spec.rubric_hash() for spec in JUDGE_METRIC_SPECS}
    try:
        from llmops.prompt_registry import register_prompt_if_changed

        for spec in JUDGE_METRIC_SPECS:
            register_prompt_if_changed(
                name=f"Judge_{spec.name}",
                template=spec.grading_prompt(),
                commit_message=f"SprintSight judge rubric {spec.name} ({spec.rubric_hash()})",
                alias=alias,
                tags={
                    "component": "llm-judge",
                    "metric": spec.name,
                    "scale": "1-5",
                    "rubric_hash": spec.rubric_hash(),
                },
            )
    except Exception:
        log.warning("Judge prompt registration skipped (registry unavailable).", exc_info=True)
    return hashes


# -- 4e. The orchestrator ----------------------------------------------------

def attach_cot_analysis(
    frame: pd.DataFrame,
    specs: Sequence[JudgeMetricSpec],
    *,
    judge_uri: str,
    parameters: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Stage one of two-stage judging: one reasoning pass per row per metric.

    Adds a ``cot_<Metric>`` column holding the evidence audit, which the
    scoring pass then receives as grading context. Costs one judge call per
    cell, so this is the expensive half of the default configuration -- the
    trade is that the score is conditioned on reasoning that was committed
    before any number was requested.

    A failed or unparseable audit is recorded as such in the column rather
    than left empty: the scoring judge must be able to see that the audit
    was unavailable instead of silently scoring without it.
    """
    enriched = frame.copy()
    context_columns = ("artifact_bundle", "gold_reference", "rubric_criteria")

    for spec in specs:
        column = spec.cot_column()
        analyses: list[str] = []
        for position, (_, row) in enumerate(enriched.iterrows(), start=1):
            grading_context = {
                name: row[name]
                for name in spec.grading_context_columns
                if name in context_columns and name in enriched.columns
            }
            prompt = spec.analysis_prompt(
                prediction=row["prediction"], grading_context=grading_context
            )
            log.info(
                "Stage-1 audit %s [%d/%d] %s / %s",
                spec.name, position, len(enriched), row["model"], row["example_id"],
            )
            try:
                raw = _judge_call(prompt, judge_uri, parameters)
                analyses.append(_format_analysis(raw))
            except Exception as error:  # noqa: BLE001 - one failed audit must not stop the run
                log.warning("Stage-1 audit failed: %s", error)
                analyses.append(
                    "EVIDENCE AUDIT UNAVAILABLE: the audit pass failed with "
                    f"{type(error).__name__}. Score from the output and the "
                    "ground-truth material alone, and note this in your "
                    "justification."
                )
        enriched[column] = analyses
    return enriched


def _format_analysis(raw: str) -> str:
    """Render a stage-one JSON audit as brace-free prose for the scoring call.

    Braces are stripped because this string is injected as grading context,
    and keeping every judge-facing string brace-free means a future change
    that routes it through PromptTemplate cannot resurrect the empty-prompt
    failure from Part 0.
    """
    if not raw or not raw.strip():
        return "EVIDENCE AUDIT UNAVAILABLE: the audit pass returned nothing."
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _strip_braces(f"EVIDENCE AUDIT (unstructured):\n{raw.strip()[:3000]}")

    def as_lines(value: Any) -> list[str]:
        if isinstance(value, list):
            return [f"- {item}" for item in value]
        return [f"- {value}"] if value else []

    sections = ["EVIDENCE AUDIT (completed before any score was requested):"]
    for key, heading in (
        ("evidence_scan", "What was checked"),
        ("anchor_check", "Rubric test results"),
        ("unresolved", "Could not be verified"),
    ):
        lines = as_lines(payload.get(key))
        if lines:
            sections += ["", f"{heading}:", *lines]
    return _strip_braces("\n".join(sections))


def run_judge_evaluation(
    records: Sequence[JudgeRecord],
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    experiment: str = JUDGE_EXPERIMENT,
    run_name: str | None = None,
    only_metrics: Sequence[str] | None = None,
    include_llm_metrics: bool = True,
    cot_mode: Literal["two_stage", "inline"] = "two_stage",
    max_workers: int = 1,
    phase: str = "preliminary",
    extra_tags: Mapping[str, str] | None = None,
) -> tuple[Any, pd.DataFrame]:
    """Run the hybrid evaluation and return (EvaluationResult, eval frame).

    ``include_llm_metrics=False`` gives the deterministic-only run: fast,
    free, and the fallback that keeps the study alive when no judge is
    available.

    ``cot_mode="two_stage"`` (default) runs a reasoning pass before scoring
    so the score is conditioned on written evidence -- see the module
    docstring, note (2), for why in-completion CoT cannot be relied on here.
    ``cot_mode="inline"`` halves the judge calls and accepts that weakness.
    """
    judge_uri = configure_judge_endpoint(judge_model)
    gold_available, only_metrics = _metrics_for_gold(records, only_metrics)

    independence: dict[str, Any] = {"independence": "not_checked"}
    if include_llm_metrics:
        # Checked BEFORE the frame is built, so a same-family judge fails
        # immediately instead of after an hour of GPU time.
        independence = assert_judge_independence(
            judge_model, [record.model for record in records]
        )

    frame = build_eval_frame(records)

    two_stage = include_llm_metrics and cot_mode == "two_stage"
    specs = selected_specs(only_metrics)
    if two_stage:
        frame = attach_cot_analysis(frame, specs, judge_uri=judge_uri)

    metrics: list[Any] = build_deterministic_metrics(frame)
    rubric_hashes: dict[str, str] = {}
    if include_llm_metrics:
        rubric_hashes = register_judge_prompts()
        metrics += build_genai_metrics(
            judge_uri,
            only=only_metrics,
            max_workers=max_workers,
            two_stage=two_stage,
        )
    if not metrics:
        raise RuntimeError("No metrics could be built for this frame.")

    # Tracking URI and experiment creation go through llmops.mlflow_config,
    # the same path services/ and evaluation/ use, rather than a second
    # mlflow.set_experiment call with its own defaults. That matters in this
    # repo specifically: mlflow_config falls back to http://localhost:5000 and
    # caches experiment ids behind a lock, so a judge run started from a
    # notebook lands in the same experiment a FastAPI-served run would.
    configure_mlflow()
    experiment_id = get_experiment_id(experiment)
    mlflow.set_experiment(experiment_id=experiment_id)
    resolved_run_name = run_name or (
        f"judge-{judge_model.replace(':', '-')}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    )

    with mlflow.start_run(run_name=resolved_run_name) as run:
        mlflow.log_params({
            "judge_model": judge_model,
            "judge_model_digest": (model_digest(judge_model) or "unknown"),
            "judge_uri": judge_uri,
            "judge_temperature": 0.0,
            "judge_seed": JUDGE_SEED,
            "judge_max_tokens": JUDGE_MAX_TOKENS,
            "rubric_scale": f"{RUBRIC_MIN}-{RUBRIC_MAX}",
            # Recorded as a param because it changes what the score MEANS:
            # two_stage scores are conditioned on a prior evidence audit and
            # are not comparable with inline scores from another run.
            "cot_mode": cot_mode if include_llm_metrics else "n/a",
            "n_rows": len(frame),
            "n_examples": int(frame["example_id"].nunique()),
            "n_candidate_models": int(frame["model"].nunique()),
            "include_llm_metrics": include_llm_metrics,
            # Without gold only the gold-free rubrics run, and judge_composite averages those.
            "gold_available": gold_available,
            "judge_metrics": ",".join(spec.name for spec in specs) if include_llm_metrics else "",
            "git_sha": git_sha(),
            "phase": phase,
            # Judge provenance: a reader must be able to tell from the run
            # alone whether self-preference bias is in play.
            "judge_family": independence.get("judge_family", "unknown"),
            "judge_independence": independence.get("independence", "not_checked"),
            "same_family_override": independence.get("same_family_override", False),
        })
        if rubric_hashes:
            mlflow.log_params({f"rubric_hash_{k}": v for k, v in rubric_hashes.items()})
        mlflow.set_tags({
            "run_type": "llm_judge_eval",
            "judge_model": judge_model,
            "phase": phase,
            **dict(extra_tags or {}),
        })

        result = mlflow.evaluate(
            data=frame,
            predictions="prediction",
            targets="target" if gold_available else None,
            model_type=None,
            extra_metrics=metrics,
            evaluators="default",
        )

        enriched = _merge_judge_scores(frame, result)
        _log_run_artifacts(
            enriched,
            judge_model=judge_model,
            cot_mode=cot_mode if include_llm_metrics else "n/a",
        )
        log.info("Judge evaluation run %s complete.", run.info.run_id)

    return result, enriched


def _metrics_for_gold(
    records: Sequence[JudgeRecord], only_metrics: Sequence[str] | None
) -> tuple[bool, Sequence[str] | None]:
    """(gold_available, rubrics to run). Every record has gold, or none does.

    A run over real sprints (no human gold) runs only the gold-free rubrics. Mixing the two in
    one run is refused: the gold-dependent rubrics would cover only part of the rows and every
    aggregate would mean something different per row.
    """
    with_gold = sum(record.gold is not None for record in records)
    if with_gold == len(records):
        return True, only_metrics
    if with_gold:
        raise ValueError(
            f"{with_gold} of {len(records)} records have gold and the rest do not; judge "
            "synthetic (gold) and real (no gold) sprints in separate runs."
        )
    requested = list(only_metrics) if only_metrics else list(JUDGE_METRIC_NAMES)
    dropped = [name for name in requested if name in GOLD_DEPENDENT_METRICS]
    kept = [name for name in requested if name not in GOLD_DEPENDENT_METRICS]
    if dropped:
        log.warning(
            "No gold for these sprints: skipping the gold-dependent rubrics %s.", ", ".join(dropped)
        )
    if not kept:
        raise ValueError(
            f"Every requested rubric needs gold ({', '.join(dropped)}); "
            f"choose from {', '.join(GOLD_FREE_METRICS)} for sprints without gold."
        )
    return False, kept


def _merge_judge_scores(frame: pd.DataFrame, result: Any) -> pd.DataFrame:
    """Attach per-row judge scores and rationales back onto the eval frame.

    MLflow's own eval table is the UI-facing copy; this is the analysis-facing
    one, and Parts 5 and 8 both need judge scores sitting next to the human
    annotations and the deterministic columns in one frame.
    """
    enriched = frame.copy()
    table = getattr(result, "tables", {}).get("eval_results_table")
    if table is None:
        log.warning("EvaluationResult carried no eval_results_table; judge scores not merged.")
        return enriched
    table = pd.DataFrame(table).reset_index(drop=True)
    enriched = enriched.reset_index(drop=True)
    for metric_name in JUDGE_METRIC_NAMES:
        for suffix in ("score", "justification"):
            source = f"{metric_name}/v1/{suffix}"
            if source in table.columns:
                enriched[f"judge_{metric_name}" if suffix == "score"
                         else f"rationale_{metric_name}"] = table[source].to_numpy()
    scored = [f"judge_{name}" for name in JUDGE_METRIC_NAMES if f"judge_{name}" in enriched]
    if scored:
        # Unweighted mean across dimensions, reported alongside the per-metric
        # columns and never instead of them: the composite is for ranking,
        # the components are for diagnosis.
        enriched["judge_composite"] = enriched[scored].apply(
            pd.to_numeric, errors="coerce"
        ).mean(axis=1)
    return enriched
