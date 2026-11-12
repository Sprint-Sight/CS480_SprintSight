"""Robustness (Part 7): self-consistency and perturbation probes.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from evaluation.offline.judge_study.config import (
    DEFAULT_JUDGE_MODEL,
    JUDGE_SEED,
    _judge_call,
    configure_judge_endpoint,
    judge_parameters,
)
from evaluation.offline.judge_study.frame import (
    JudgeRecord,
    render_assessment_for_judge,
    render_bundle_for_judge,
    render_gold_for_judge,
    render_rubric_criteria,
)
from evaluation.offline.judge_study.meta import krippendorff_alpha_ordinal
from evaluation.offline.judge_study.specs import SPEC_BY_NAME
from evaluation.stats import bootstrap_ci

#
# A judge score is only usable if re-running it tomorrow gives roughly the
# same answer. Two distinct questions, and conflating them is a common error:
#
#   Self-consistency: same prompt, repeated sampling. Measures decoding
#     noise. Reported as per-row SD and as Krippendorff's alpha across
#     replicates, which is intra-rater reliability in the psychometric sense.
#   Perturbation sensitivity: semantically NEUTRAL edits to the candidate
#     text. Measures whether the judge is reading the content or reacting to
#     its presentation. Any non-zero mean shift here is a bias, because the
#     edit by construction changed nothing that should matter.
#
# The perturbations are chosen to target documented LLM-judge biases:
#   dimension_order   position/primacy effects within a single output
#   verbosity_padding verbosity bias -- the single best-replicated finding in
#                     the LLM-judge literature. The padding adds words and
#                     zero information, so a positive shift is pure bias.
#   whitespace        a floor control. Any shift here is noise, and it
#                     calibrates how much of the other shifts to believe.


def _perturb_identity(text: str, rng: random.Random) -> str:
    return text


def _perturb_dimension_order(text: str, rng: random.Random) -> str:
    """Shuffle the per-dimension blocks, preserving every character of content."""
    lines = text.split("\n")
    try:
        start = lines.index("Per-dimension assessment:") + 1
    except ValueError:
        return text
    end = start
    while end < len(lines) and (lines[end].startswith("- ") or lines[end].startswith("  ")):
        end += 1
    blocks: list[list[str]] = []
    for line in lines[start:end]:
        if line.startswith("- ") or not blocks:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    if len(blocks) < 2:
        return text
    rng.shuffle(blocks)
    reordered = [line for block in blocks for line in block]
    return "\n".join(lines[:start] + reordered + lines[end:])


_PADDING = (
    ("This analysis was conducted with careful attention to the available "
    "evidence and reflects a considered review of the sprint as a whole."),
    ("The observations above are offered in a constructive spirit and are "
    "intended to support the team's continued development."),
    ("Each dimension was considered in turn, with the available artifacts "
    "taken into account throughout the review process."),
)


def _perturb_verbosity(text: str, rng: random.Random) -> str:
    """Append fluent, information-free prose. Tests verbosity bias directly."""
    return text + "\n\n" + "\n".join(_PADDING)


def _perturb_whitespace(text: str, rng: random.Random) -> str:
    """Control condition: reformat only."""
    return "\n".join(
        line + ("  " if rng.random() < 0.5 else "") for line in text.split("\n")
    )


PERTURBATIONS: dict[str, Callable[[str, random.Random], str]] = {
    "identity": _perturb_identity,
    "dimension_order": _perturb_dimension_order,
    "verbosity_padding": _perturb_verbosity,
    "whitespace": _perturb_whitespace,
}


def self_consistency_probe(
    records: Sequence[JudgeRecord],
    *,
    metrics: Sequence[str] = ("Code_Faithfulness", "Bug_Actionability"),
    judge_model: str = DEFAULT_JUDGE_MODEL,
    replicates: int = 3,
    temperatures: Sequence[float] = (0.0, 0.3, 0.7),
    perturbations: Sequence[str] = ("identity", "dimension_order", "verbosity_padding"),
    seed: int = 42,
) -> pd.DataFrame:
    """Re-grade each row under repeated sampling and neutral perturbations.

    Returns one row per (example, model, metric, perturbation, replicate)
    with the score and the decoding settings that produced it, so the caller
    can aggregate however the question demands. Defaults to two metrics and
    three perturbations because the call count is
    rows * metrics * perturbations * replicates and this runs on one local
    GPU -- the probe is a diagnostic on a sample, not a full re-evaluation.
    """
    judge_uri = configure_judge_endpoint(judge_model)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []

    from mlflow.metrics.genai.genai_metric import _extract_score_and_justification

    for record in records:
        base_text = render_assessment_for_judge(record.candidate, record.error)
        context_values = {
            "artifact_bundle": render_bundle_for_judge(record.bundle),
            "gold_reference": render_gold_for_judge(record.gold),
            "rubric_criteria": render_rubric_criteria(),
        }
        inputs = (
            f"Grade sprint {record.bundle.sprint_id} for team {record.bundle.team_id}."
        )
        for metric_name in metrics:
            spec = SPEC_BY_NAME[metric_name]
            grading_context = {
                column: context_values[column] for column in spec.grading_context_columns
            }
            for perturbation_name in perturbations:
                perturbed = PERTURBATIONS[perturbation_name](base_text, rng)
                for replicate in range(replicates):
                    temperature = temperatures[replicate % len(temperatures)]
                    # A distinct seed per replicate: reusing one seed at
                    # temperature 0 would return the identical completion and
                    # report a fake SD of zero.
                    parameters = judge_parameters(
                        temperature=temperature, seed=JUDGE_SEED + replicate
                    )
                    prompt = spec.eval_prompt_for(
                        judge_uri=judge_uri,
                        prediction=perturbed,
                        inputs=inputs,
                        grading_context=grading_context,
                        parameters=parameters,
                    )
                    try:
                        raw = _judge_call(prompt, judge_uri, parameters)
                        score, justification = _extract_score_and_justification(raw)
                    except Exception as error:  # noqa: BLE001
                        score, justification = None, f"judge call failed: {error}"
                    rows.append({
                        "example_id": record.example_id,
                        "model": record.model,
                        "metric": metric_name,
                        "perturbation": perturbation_name,
                        "replicate": replicate,
                        "temperature": temperature,
                        "score": score,
                        "justification": justification,
                    })

    return pd.DataFrame(rows)


def consistency_summary(probe: pd.DataFrame) -> pd.DataFrame:
    """Per-metric decoding noise and intra-rater reliability."""
    if probe.empty:
        return pd.DataFrame()
    identity = probe[probe["perturbation"] == "identity"].copy()
    if identity.empty:
        return pd.DataFrame()
    identity["score"] = pd.to_numeric(identity["score"], errors="coerce")

    rows = []
    for metric_name, group in identity.groupby("metric"):
        wide = group.pivot_table(
            index="replicate", columns=["example_id", "model"], values="score"
        )
        per_row_sd = group.groupby(["example_id", "model"])["score"].std(ddof=1)
        rows.append({
            "metric": metric_name,
            "n_items": int(wide.shape[1]),
            "n_replicates": int(wide.shape[0]),
            "mean_within_item_sd": float(per_row_sd.mean()) if not per_row_sd.empty else None,
            "max_within_item_sd": float(per_row_sd.max()) if not per_row_sd.empty else None,
            # Alpha across replicates = intra-rater reliability. Below about
            # 0.67 the judge is too noisy for the per-example scores to be
            # reported individually, whatever its agreement with humans.
            "intra_rater_alpha": krippendorff_alpha_ordinal(wide.to_numpy()),
            "unparseable_rate": float(group["score"].isna().mean()),
        })
    return pd.DataFrame(rows).set_index("metric")


def perturbation_summary(probe: pd.DataFrame) -> pd.DataFrame:
    """Mean score shift caused by each semantically neutral perturbation.

    The shift is computed against the identity condition on the SAME item, so
    it is a paired estimate and item difficulty cancels out. A CI that
    excludes zero means the judge is measurably reacting to presentation
    rather than content -- the number to quote when a stakeholder asks how
    much the judge can be gamed.
    """
    if probe.empty:
        return pd.DataFrame()
    local = probe.copy()
    local["score"] = pd.to_numeric(local["score"], errors="coerce")
    baseline = (
        local[local["perturbation"] == "identity"]
        .groupby(["metric", "example_id", "model"])["score"]
        .mean()
        .rename("baseline")
    )
    rows = []
    for (metric_name, perturbation_name), group in local.groupby(["metric", "perturbation"]):
        if perturbation_name == "identity":
            continue
        merged = (
            group.groupby(["metric", "example_id", "model"])["score"]
            .mean()
            .rename("perturbed")
            .to_frame()
            .join(baseline, how="inner")
            .dropna()
        )
        if merged.empty:
            continue
        deltas = (merged["perturbed"] - merged["baseline"]).to_numpy()
        point, low, high = bootstrap_ci(deltas.tolist())
        rows.append({
            "metric": metric_name,
            "perturbation": perturbation_name,
            "n_items": len(deltas),
            "mean_delta": point,
            "ci_low": low,
            "ci_high": high,
            "max_abs_delta": float(np.max(np.abs(deltas))),
            "biased": bool(
                low is not None and high is not None and (low > 0 or high < 0)
            ),
        })
    return pd.DataFrame(rows)
