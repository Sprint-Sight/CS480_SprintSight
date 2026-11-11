"""Artifacts (Part 9): figures, the error taxonomy and the judge card.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import mlflow
import numpy as np
import pandas as pd

from evaluation.offline.judge_study.config import (
    JUDGE_BUNDLE_CHAR_BUDGET,
    JUDGE_MAX_TOKENS,
    JUDGE_SEED,
    RUBRIC_MAX,
    RUBRIC_MIN,
)
from evaluation.offline.judge_study.meta import calibration_table
from evaluation.offline.judge_study.specs import JUDGE_METRIC_NAMES, JUDGE_METRIC_SPECS
from evaluation.offline.provenance import git_sha, model_digest
from evaluation.stats import is_nan
from prompts.dimension_criteria import DIMENSIONS

log = logging.getLogger(__name__)


#
# Everything here is logged to the MLflow run, because a number in a notebook
# that nobody can trace back to the run that produced it is not a result. The
# judge card in particular is the artifact a stakeholder should be handed
# first: it states what the judge is, how well it agrees with humans, how
# biased it is, and what it cannot be used for.

# Error taxonomy. Each category is detected by a deterministic rule over the
# precomputed columns and the judge's own rationale text -- so the taxonomy is
# reproducible and auditable, rather than a second LLM pass whose own errors
# would need validating.
ERROR_TAXONOMY: dict[str, str] = {
    "no_output": "The candidate model produced no parseable assessment at all.",
    "schema_invalid": "Output present but failed SprintAssessment validation.",
    "fabricated_citation": "At least one citation does not resolve to the bundle.",
    "unanchored_evidence": "Citations carry no commit SHA, ticket key or filename.",
    "incomplete_coverage": "One or more rubric dimensions missing or failed.",
    "generic_recommendation": "Recommendations are filler with no assignable action.",
    "score_inflation": "Scores sit materially above the human reference.",
    "score_deflation": "Scores sit materially below the human reference.",
    "invalid_inference": "Judge flagged an unsupported evidence-to-judgement leap.",
    "clean": "No rule fired for this row.",
}

_INVALID_INFERENCE_CUES = (
    "lines added",
    "churn",
    "proxy",
    "does not follow",
    "conflat",
    "coverage",
    "invalid inference",
    "t3 failed",
    "t4 failed",
)


def classify_errors(frame: pd.DataFrame) -> pd.DataFrame:
    """Tag every row with the error categories whose rules fire for it.

    Multi-label on purpose: a row can be both unanchored and inflated, and
    forcing a single label would hide one of the two defects a maintainer
    needs to fix.
    """
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        tags: list[str] = []
        if row.get("error") or row.get("dimensions_present", 0) == 0:
            tags.append("no_output")
        if row.get("schema_valid") is False:
            tags.append("schema_invalid")

        # groundedness_rate comes from evaluation.offline.metrics, not from a
        # second implementation here -- see citation_anchor_metrics.
        grounded = row.get("groundedness_rate")
        if grounded is not None and not is_nan(grounded) and grounded < 1.0:
            tags.append("fabricated_citation")

        anchor = row.get("citation_anchor_rate")
        if anchor is not None and not is_nan(anchor) and anchor < 0.5:
            tags.append("unanchored_evidence")

        scored = row.get("dimensions_present")
        if scored is not None and not is_nan(scored) and 0 < scored < len(DIMENSIONS):
            tags.append("incomplete_coverage")

        warnings = row.get("lint_warnings")
        if isinstance(warnings, str) and "generic_recommendation" in warnings:
            tags.append("generic_recommendation")

        signed = row.get("grade_signed_error_overall")
        if signed is not None and not is_nan(signed):
            if signed >= 1.5:
                tags.append("score_inflation")
            elif signed <= -1.5:
                tags.append("score_deflation")

        rationale = " ".join(
            str(row.get(f"rationale_{name}", "")) for name in JUDGE_METRIC_NAMES
        ).lower()
        correctness = row.get("judge_Technical_Correctness")
        if (
            correctness is not None
            and not is_nan(correctness)
            and float(correctness) <= 3
            and any(cue in rationale for cue in _INVALID_INFERENCE_CUES)
        ):
            tags.append("invalid_inference")

        if not tags:
            tags.append("clean")
        for tag in tags:
            records.append({
                "example_id": row.get("example_id"),
                "model": row.get("model"),
                "category": tag,
            })
    return pd.DataFrame(records)


def taxonomy_counts(classified: pd.DataFrame) -> pd.DataFrame:
    if classified.empty:
        return pd.DataFrame()
    counts = (
        classified.groupby(["model", "category"]).size().rename("count").reset_index()
    )
    return counts.pivot(index="category", columns="model", values="count").fillna(0)


def _figure(width: float = 7.0, height: float = 4.5):
    import matplotlib

    matplotlib.use("Agg")  # headless: these run in CI and over SSH
    import matplotlib.pyplot as plt

    return plt.subplots(figsize=(width, height))


def radar_figure(frame: pd.DataFrame) -> Any | None:
    """Per-model profile across the five judge dimensions.

    A radar plot is the right form here and a poor one in general: it works
    because all five axes share one 1-5 scale and the question is shape, not
    magnitude. The axes are labelled with their scale so the figure cannot be
    read as percentages.
    """
    import matplotlib.pyplot as plt

    columns = [f"judge_{name}" for name in JUDGE_METRIC_NAMES if f"judge_{name}" in frame.columns]
    if len(columns) < 3 or "model" not in frame.columns:
        return None
    means = frame.groupby("model")[columns].apply(
        lambda group: group.apply(pd.to_numeric, errors="coerce").mean()
    )
    if means.empty:
        return None

    angles = np.linspace(0, 2 * np.pi, len(columns), endpoint=False).tolist()
    angles += angles[:1]
    figure, axis = plt.subplots(figsize=(6.5, 6.5), subplot_kw={"polar": True})
    for model, row in means.iterrows():
        values = row.tolist()
        values += values[:1]
        axis.plot(angles, values, label=str(model), linewidth=1.8)
        axis.fill(angles, values, alpha=0.08)
    axis.set_xticks(angles[:-1])
    axis.set_xticklabels([column.replace("judge_", "").replace("_", " ") for column in columns],
                         fontsize=9)
    axis.set_ylim(RUBRIC_MIN - 0.2, RUBRIC_MAX + 0.2)
    axis.set_yticks(range(RUBRIC_MIN, RUBRIC_MAX + 1))
    axis.set_title("LLM-judge profile by model (1-5 rubric, higher is better)", pad=24)
    axis.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
    figure.tight_layout()
    return figure


def confusion_figure(frame: pd.DataFrame, metric: str) -> Any | None:
    """Judge-vs-human confusion matrix for one metric.

    The off-diagonal STRUCTURE is the point, not the diagonal mass: cells
    clustered above the diagonal mean a systematically lenient judge, which
    is a correctable prompt problem, while scatter in both directions means
    noise, which is not.
    """
    judge_column, human_column = f"judge_{metric}", f"human_{metric}"
    if judge_column not in frame.columns or human_column not in frame.columns:
        return None
    paired = frame[[human_column, judge_column]].apply(pd.to_numeric, errors="coerce").dropna()
    if paired.empty:
        return None

    levels = list(range(RUBRIC_MIN, RUBRIC_MAX + 1))
    matrix = np.zeros((len(levels), len(levels)), dtype=int)
    for human_value, judge_value in paired.to_numpy():
        human_index = round(human_value) - RUBRIC_MIN
        judge_index = round(judge_value) - RUBRIC_MIN
        if 0 <= human_index < len(levels) and 0 <= judge_index < len(levels):
            matrix[human_index, judge_index] += 1

    figure, axis = _figure(5.6, 5.0)
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(levels)), [str(level) for level in levels])
    axis.set_yticks(range(len(levels)), [str(level) for level in levels])
    axis.set_xlabel("LLM judge score")
    axis.set_ylabel("Human annotator score")
    axis.set_title(f"{metric}: judge vs human (n={len(paired)})")
    for i in range(len(levels)):
        for j in range(len(levels)):
            if matrix[i, j]:
                axis.text(j, i, str(matrix[i, j]), ha="center", va="center",
                          color="white" if matrix[i, j] > matrix.max() / 2 else "black")
    figure.colorbar(image, ax=axis, shrink=0.8, label="rows")
    figure.tight_layout()
    return figure


def agreement_figure(frame: pd.DataFrame, metric: str) -> Any | None:
    """Scatter with identity line, plus a Bland-Altman panel.

    Bland-Altman is the clinical standard for method comparison and belongs
    here for the same reason: it separates bias (where the mean-difference
    line sits) from precision (how wide the limits of agreement are). A
    correlation coefficient conflates the two, and for a grading tool the
    bias is the part a student would feel.
    """
    judge_column, human_column = f"judge_{metric}", f"human_{metric}"
    if judge_column not in frame.columns or human_column not in frame.columns:
        return None
    paired = frame[[human_column, judge_column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(paired) < 3:
        return None

    import matplotlib.pyplot as plt

    human_values = paired[human_column].to_numpy(dtype=float)
    judge_values = paired[judge_column].to_numpy(dtype=float)
    figure, (left, right) = plt.subplots(1, 2, figsize=(10.5, 4.4))

    jitter = np.random.default_rng(0).normal(0, 0.04, size=len(paired))
    left.scatter(human_values + jitter, judge_values + jitter, alpha=0.7, s=40)
    left.plot([RUBRIC_MIN, RUBRIC_MAX], [RUBRIC_MIN, RUBRIC_MAX], "--", color="grey",
              linewidth=1, label="perfect agreement")
    left.set_xlabel("Human score")
    left.set_ylabel("Judge score")
    left.set_title(f"{metric} (n={len(paired)}, jittered)")
    left.legend(fontsize=8)

    means = (human_values + judge_values) / 2
    differences = judge_values - human_values
    bias = float(differences.mean())
    sd = float(differences.std(ddof=1)) if len(differences) >= 2 else 0.0
    right.scatter(means, differences, alpha=0.7, s=40)
    right.axhline(0, color="grey", linestyle=":", linewidth=1)
    right.axhline(bias, color="crimson", linewidth=1.2, label=f"bias={bias:+.2f}")
    right.axhline(bias + 1.96 * sd, color="crimson", linestyle="--", linewidth=0.9,
                  label="95% limits of agreement")
    right.axhline(bias - 1.96 * sd, color="crimson", linestyle="--", linewidth=0.9)
    right.set_xlabel("Mean of judge and human")
    right.set_ylabel("Judge minus human")
    right.set_title("Bland-Altman")
    right.legend(fontsize=8)
    figure.tight_layout()
    return figure


def taxonomy_figure(counts: pd.DataFrame) -> Any | None:
    if counts.empty:
        return None
    figure, axis = _figure(8.0, 4.8)
    counts.plot(kind="barh", ax=axis, width=0.78)
    axis.set_xlabel("rows matching category")
    axis.set_ylabel("")
    axis.set_title("Error taxonomy by candidate model (rows may match several)")
    axis.legend(fontsize=8, title="model")
    figure.tight_layout()
    return figure


def judge_card(
    *,
    judge_model: str,
    frame: pd.DataFrame,
    cot_mode: str = "two_stage",
    calibration: pd.DataFrame | None = None,
    pairwise_diagnostics: Mapping[str, float] | None = None,
    consistency: pd.DataFrame | None = None,
    perturbation: pd.DataFrame | None = None,
) -> str:
    """A model card for the JUDGE, in the datasheet tradition.

    This is the stakeholder-facing artifact. It exists because the usual
    failure of an LLM-judge report is not a wrong number, it is a number
    presented without the information needed to discount it. Everything here
    is read from the run's own outputs, so it cannot drift from the results
    it describes.
    """
    lines = [
        "# SprintSight LLM-as-a-Judge -- evaluation card",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M UTC} | git {git_sha()}",
        "",
        "## 1. What this judge is",
        "",
        f"- Judge model: `{judge_model}` (digest `{(model_digest(judge_model) or "unknown")}`)",
        f"- Served locally over Ollama's OpenAI-compatible endpoint as `openai:/{judge_model}`",
        (f"- Decoding: temperature 0.0, top_p 1.0, seed {JUDGE_SEED}, "
        f"max_tokens {JUDGE_MAX_TOKENS}, JSON response mode"),
        (f"- Rubric: {len(JUDGE_METRIC_SPECS)} dimensions, each a 1-5 scale with written "
        "anchors and two few-shot exemplars"),
        f"- Reasoning: {cot_mode}. "
        + (
            "A separate evidence-audit call establishes the per-rubric-test "
            "findings with no score field available; that audit is then supplied "
            "to the scoring call as grading context, so the score is conditioned "
            "on reasoning committed beforehand."
            if cot_mode == "two_stage"
            else "Single-call scoring. Reasoning-first JSON is requested but "
            "MLflow appends its own score-first instruction afterwards, so the "
            "score may be emitted before any reasoning. Treat these scores as "
            "weaker evidence than two_stage scores and do not mix the two."
        ),
        "",
        "Rubric hashes (change these and prior scores stop being comparable):",
        "",
    ]
    for spec in JUDGE_METRIC_SPECS:
        lines.append(f"- `{spec.name}`: `{spec.rubric_hash()}`")

    lines += [
        "",
        "## 2. Agreement with human annotators",
        "",
    ]
    if calibration is not None and not calibration.empty:
        lines += [
            ("| Metric | n | quad. kappa [95% CI] | Spearman rho | ICC(2,1) | "
            "bias (judge-human) | reading |"),
            "|---|---|---|---|---|---|---|",
        ]
        for metric_name, row in calibration.iterrows():
            def show(value: Any, digits: int = 2) -> str:
                return "n/a" if value is None or is_nan(value) else f"{float(value):.{digits}f}"

            ci = (
                f" [{show(row.get('quadratic_kappa_ci_low'))}, "
                f"{show(row.get('quadratic_kappa_ci_high'))}]"
                if row.get("quadratic_kappa_ci_low") is not None
                else ""
            )
            lines.append(
                f"| {metric_name} | {int(row.get('n', 0))} | "
                f"{show(row.get('quadratic_kappa'))}{ci} | "
                f"{show(row.get('spearman_rho'))} | {show(row.get('icc_2_1'))} | "
                f"{show(row.get('mean_signed_error'))} | "
                f"{row.get('interpretation', 'n/a')} |"
            )
        warned = [
            f"- `{metric_name}`: {row['warnings']}"
            for metric_name, row in calibration.iterrows()
            if row.get("warnings")
        ]
        if warned:
            lines += ["", "Caveats raised during calibration:", ""] + warned
    else:
        lines.append(
            "**No human annotations were supplied, so this judge is UNVALIDATED.** "
            "Its scores may be reported as a relative ranking signal only, never "
            "as a measure of assessment quality, and never to a student."
        )

    lines += ["", "## 3. Known biases, measured", ""]
    if pairwise_diagnostics:
        bias_rate = pairwise_diagnostics.get("position_bias_rate")
        lines += [
            f"- Position bias rate: **{bias_rate:.1%}** of comparisons picked "
            "whichever candidate was shown first, in both presentation orders"
            if bias_rate is not None else "- Position bias rate: not measured",
            (f"- Swap consistency: {pairwise_diagnostics.get('swap_consistency_rate', float('nan')):.1%} "
            "of comparisons survived an order swap and are counted in the win matrix"),
            f"- Unparseable verdicts: {pairwise_diagnostics.get('unparseable_rate', float('nan')):.1%}",
        ]
    else:
        lines.append("- Position bias: not measured in this run.")

    if perturbation is not None and not perturbation.empty:
        for _, row in perturbation.iterrows():
            verdict = "BIASED" if row.get("biased") else "within noise"
            lines.append(
                f"- `{row['metric']}` under `{row['perturbation']}`: mean shift "
                f"{row['mean_delta']:+.2f} "
                f"[{row['ci_low']:+.2f}, {row['ci_high']:+.2f}] -- {verdict}"
            )
    else:
        lines.append("- Perturbation sensitivity: not measured in this run.")

    lines += ["", "## 4. Self-consistency", ""]
    if consistency is not None and not consistency.empty:
        for metric_name, row in consistency.iterrows():
            alpha = row.get("intra_rater_alpha")
            lines.append(
                f"- `{metric_name}`: within-item SD "
                f"{row.get('mean_within_item_sd', float('nan')):.2f} over "
                f"{int(row.get('n_replicates', 0))} replicates, intra-rater alpha "
                f"{'n/a' if alpha is None or is_nan(alpha) else format(float(alpha), '.2f')}"
            )
    else:
        lines.append("- Not measured in this run.")

    lines += [
        "",
        "## 5. Scope and limits",
        "",
        ("- Validated only on the fixtures and sprints in this run's dataset. "
        "Scores on other course structures or other rubrics are out of scope."),
        ("- The judge grades the GRADER, never a student. It has no access to "
        "student identities beyond the commit authors already in the bundle."),
        (f"- Bundles are truncated at {JUDGE_BUNDLE_CHAR_BUDGET} characters, announced "
        "in-prompt. Faithfulness judgements on sprints larger than this are "
        "measured against a partial view of the evidence."),
        ("- Numeric grade accuracy and rank ordering are computed arithmetically, "
        "not judged, and are unaffected by anything in sections 2 to 4."),
        ("- A judge sharing a model family with a candidate under test is subject "
        "to self-preference bias; prefer a judge from a different family and "
        "record the choice here."),
        "",
        "## 6. How to read the headline numbers",
        "",
        ("Per-example judge scores are reportable only where intra-rater alpha is "
        "at least 0.67 and quadratic kappa against humans is at least 0.61. Below "
        "those thresholds, report aggregate model rankings with CIs and say "
        "explicitly that per-example scores are not reliable."),
        "",
        (f"Rows in this run: {len(frame)} | "
        f"candidate models: {frame['model'].nunique() if 'model' in frame else 0} | "
        f"examples: {frame['example_id'].nunique() if 'example_id' in frame else 0}"),
    ]
    return "\n".join(lines)


def _log_run_artifacts(
    frame: pd.DataFrame, *, judge_model: str, cot_mode: str = "two_stage"
) -> None:
    """Log the analysis-facing frame, figures and taxonomy to the active run."""
    try:
        mlflow.log_table(frame, artifact_file="judge_eval_rows.json")
    except Exception:
        log.warning("Could not log judge_eval_rows table.", exc_info=True)

    try:
        classified = classify_errors(frame)
        counts = taxonomy_counts(classified)
        if not counts.empty:
            mlflow.log_dict(
                {
                    "definitions": ERROR_TAXONOMY,
                    "counts": json.loads(counts.to_json()),
                },
                "error_taxonomy.json",
            )
            figure = taxonomy_figure(counts)
            if figure is not None:
                mlflow.log_figure(figure, "figures/error_taxonomy.png")
    except Exception:
        log.warning("Error taxonomy artifact failed.", exc_info=True)

    try:
        figure = radar_figure(frame)
        if figure is not None:
            mlflow.log_figure(figure, "figures/judge_radar.png")
    except Exception:
        log.warning("Radar figure failed.", exc_info=True)

    calibration: pd.DataFrame | None = None
    if any(f"human_{name}" in frame.columns for name in JUDGE_METRIC_NAMES):
        try:
            calibration = calibration_table(frame)
            mlflow.log_table(
                calibration.reset_index(), artifact_file="judge_calibration.json"
            )
            for metric_name in JUDGE_METRIC_NAMES:
                for builder, path in (
                    (confusion_figure, "figures/confusion_{}.png"),
                    (agreement_figure, "figures/agreement_{}.png"),
                ):
                    figure = builder(frame, metric_name)
                    if figure is not None:
                        mlflow.log_figure(figure, path.format(metric_name))
            # Calibration coefficients are first-class metrics, not just an
            # artifact: a reviewer filtering runs in the MLflow UI must be
            # able to sort by judge reliability.
            for index_value, row in calibration.iterrows():
                metric_name = str(index_value)
                for column in ("quadratic_kappa", "cohen_kappa", "spearman_rho",
                               "icc_2_1", "mean_signed_error", "mae"):
                    value = row.get(column)
                    if value is not None and not is_nan(value):
                        mlflow.log_metric(f"calib_{column}_{metric_name}", float(value))
        except Exception:
            log.warning("Calibration artifacts failed.", exc_info=True)

    try:
        card = judge_card(
            judge_model=judge_model,
            frame=frame,
            cot_mode=cot_mode,
            calibration=calibration,
        )
        mlflow.log_text(card, "judge_card.md")
    except Exception:
        log.warning("Judge card failed.", exc_info=True)
