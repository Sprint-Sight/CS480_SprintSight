"""Bias mitigation (Part 6): pairwise comparison with position-swap debiasing.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from evaluation.offline.judge_study.config import (
    DEFAULT_JUDGE_MODEL,
    _judge_call,
    configure_judge_endpoint,
)
from evaluation.offline.judge_study.frame import (
    JudgeRecord,
    render_assessment_for_judge,
    render_bundle_for_judge,
    render_gold_for_judge,
)

log = logging.getLogger(__name__)


_PAIRWISE_PROMPT = """You are an impartial evaluator of two AI-generated software \
engineering sprint assessments. Both were produced from the SAME ground-truth \
artifacts, shown below.

Decide which assessment is more useful to a course instructor, judging ONLY:
  1. Faithfulness: does every claim trace to the ground-truth artifacts?
  2. Specificity: are commit SHAs, ticket keys and filenames cited, not vague prose?
  3. Actionability: do the recommendations name a concrete next step aimed at the
     team's real weakest area?
  4. Technical validity: are the inferences from evidence to judgement sound?

Ignore length, tone, formatting and confidence. A shorter assessment that cites
real evidence is better than a longer one that does not.

GROUND-TRUTH ARTIFACTS:
{bundle}

HUMAN REFERENCE SCORES:
{gold}

ASSESSMENT A:
{assessment_a}

ASSESSMENT B:
{assessment_b}

Reply with a single JSON object and nothing else, with its keys in exactly this \
order so your reasoning is written before your verdict:
  "comparison": a 1-3 sentence comparison naming the decisive difference,
  "decisive_criterion": one of faithfulness, specificity, actionability, technical_validity,
  "winner": exactly one of "A", "B", or "TIE". Use TIE only if they are genuinely
  indistinguishable on the four criteria above.
"""

_WINNER_PATTERN = re.compile(r'"?winner"?\s*[:=]\s*"?\s*(A|B|TIE)\b', re.IGNORECASE)


def _parse_winner(raw: str) -> tuple[str | None, str]:
    """Extract the verdict and the judge's stated reasoning."""
    if not raw:
        return None, "empty judge response"
    try:
        payload = json.loads(raw)
        winner = str(payload.get("winner", "")).strip().upper()
        reasoning = str(payload.get("comparison", ""))
        if winner in {"A", "B", "TIE"}:
            return winner, reasoning
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    match = _WINNER_PATTERN.search(raw)
    if match:
        return match.group(1).upper(), raw[:400]
    return None, f"unparseable verdict: {raw[:200]}"


@dataclass
class PairwiseOutcome:
    """One position-swapped comparison between two candidate models."""

    example_id: str
    model_a: str
    model_b: str
    # Verdicts are recorded in terms of the MODELS, not of the slots, so a
    # reader never has to re-derive which "A" meant which model.
    winner_forward: str | None  # model_a shown first
    winner_reversed: str | None  # model_b shown first
    consistent: bool
    winner: str | None  # model name, "tie", or None when inconsistent
    position_bias: bool
    reasoning_forward: str = ""
    reasoning_reversed: str = ""

    def to_row(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "model_a": self.model_a,
            "model_b": self.model_b,
            "winner_forward": self.winner_forward,
            "winner_reversed": self.winner_reversed,
            "consistent": self.consistent,
            "winner": self.winner,
            "position_bias": self.position_bias,
            "reasoning_forward": self.reasoning_forward,
            "reasoning_reversed": self.reasoning_reversed,
        }


def pairwise_compare(
    record_a: JudgeRecord,
    record_b: JudgeRecord,
    *,
    judge_uri: str,
    parameters: Mapping[str, Any] | None = None,
) -> PairwiseOutcome:
    """Compare two candidates on one example, in both presentation orders."""
    if record_a.example_id != record_b.example_id:
        raise ValueError(
            "Pairwise comparison requires the same example: got "
            f"{record_a.example_id!r} and {record_b.example_id!r}"
        )

    bundle = render_bundle_for_judge(record_a.bundle)
    gold = render_gold_for_judge(record_a.gold)
    text_a = render_assessment_for_judge(record_a.candidate, record_a.error)
    text_b = render_assessment_for_judge(record_b.candidate, record_b.error)

    forward_raw = _judge_call(
        _PAIRWISE_PROMPT.format(
            bundle=bundle, gold=gold, assessment_a=text_a, assessment_b=text_b
        ),
        judge_uri,
        parameters,
    )
    reversed_raw = _judge_call(
        _PAIRWISE_PROMPT.format(
            bundle=bundle, gold=gold, assessment_a=text_b, assessment_b=text_a
        ),
        judge_uri,
        parameters,
    )

    forward_slot, forward_reason = _parse_winner(forward_raw)
    reversed_slot, reversed_reason = _parse_winner(reversed_raw)

    # Translate slot verdicts into model names. In the reversed call, slot A
    # held model_b.
    forward_model = {
        "A": record_a.model, "B": record_b.model, "TIE": "tie", None: None
    }[forward_slot]
    reversed_model = {
        "A": record_b.model, "B": record_a.model, "TIE": "tie", None: None
    }[reversed_slot]

    consistent = (
        forward_model is not None
        and reversed_model is not None
        and forward_model == reversed_model
    )
    # Position bias specifically: both orders picked the first-shown slot, so
    # the judge preferred the POSITION rather than either model.
    position_bias = forward_slot == "A" and reversed_slot == "A"

    return PairwiseOutcome(
        example_id=record_a.example_id,
        model_a=record_a.model,
        model_b=record_b.model,
        winner_forward=forward_model,
        winner_reversed=reversed_model,
        consistent=consistent,
        winner=forward_model if consistent else None,
        position_bias=position_bias,
        reasoning_forward=forward_reason,
        reasoning_reversed=reversed_reason,
    )


def pairwise_tournament(
    records: Sequence[JudgeRecord],
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    parameters: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Round-robin over every model pair on every shared example.

    Returns (per-comparison rows, win matrix, diagnostics). Cost is
    2 * C(models, 2) * examples judge calls, which is why the win rates are
    computed on CONSISTENT verdicts only: paying twice per comparison buys
    the right to discard the half of the signal that turns out to be noise.
    """
    judge_uri = configure_judge_endpoint(judge_model)
    by_example: dict[str, list[JudgeRecord]] = {}
    for record in records:
        by_example.setdefault(record.example_id, []).append(record)

    outcomes: list[PairwiseOutcome] = []
    for example_id, group in sorted(by_example.items()):
        unique_models = sorted({record.model for record in group})
        by_model = {record.model: record for record in group}
        for index, model_a in enumerate(unique_models):
            for model_b in unique_models[index + 1:]:
                log.info("Pairwise %s: %s vs %s", example_id, model_a, model_b)
                outcomes.append(
                    pairwise_compare(
                        by_model[model_a],
                        by_model[model_b],
                        judge_uri=judge_uri,
                        parameters=parameters,
                    )
                )

    rows = pd.DataFrame([outcome.to_row() for outcome in outcomes])
    if rows.empty:
        return rows, pd.DataFrame(), {"n_comparisons": 0.0}

    consistent = rows[rows["consistent"]]
    models = sorted(set(rows["model_a"]) | set(rows["model_b"]))
    matrix = pd.DataFrame(0.0, index=models, columns=models)
    for _, row in consistent.iterrows():
        if row["winner"] in (None, "tie"):
            # A surviving tie is genuine information: half a win each, the
            # standard Bradley-Terry treatment.
            matrix.loc[row["model_a"], row["model_b"]] += 0.5
            matrix.loc[row["model_b"], row["model_a"]] += 0.5
            continue
        loser = row["model_b"] if row["winner"] == row["model_a"] else row["model_a"]
        matrix.loc[row["winner"], loser] += 1.0

    diagnostics = {
        "n_comparisons": float(len(rows)),
        "n_judge_calls": float(2 * len(rows)),
        # The headline bias figure. Above roughly 0.2 and the pairwise
        # verdicts should not be reported as a model ranking at all.
        "position_bias_rate": float(rows["position_bias"].mean()),
        "swap_consistency_rate": float(rows["consistent"].mean()),
        "unparseable_rate": float(
            rows[["winner_forward", "winner_reversed"]].isna().any(axis=1).mean()
        ),
        "tie_rate": float((consistent["winner"] == "tie").mean()) if len(consistent) else 0.0,
    }
    log.info("Pairwise diagnostics: %s", diagnostics)
    return rows, matrix, diagnostics
