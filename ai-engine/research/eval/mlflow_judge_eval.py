"""LLM-as-a-Judge evaluation framework for SprintSight, built on MLflow.

This module is the *measurement* layer for the model-comparison study. It
answers two different questions and keeps them strictly apart:

  Q1 (evaluation)      How good is a candidate model's SprintAssessment?
  Q2 (meta-evaluation) How much should anyone believe Q1's answer?

Most LLM-judge code only answers Q1, which makes the resulting numbers
unfalsifiable: a judge that agrees with nobody still produces a tidy mean.
Everything from Part 5 onwards exists to put an error bar and a reliability
coefficient on the judge itself, so a reader can discount our headline
numbers by a known amount instead of an unknown one.

Architecture
------------
Part 0  Judge endpoint configuration (local Ollama via MLflow's openai URI)
Part 1  Rubric anchors, chain-of-thought protocol, few-shot calibration
Part 2  Native MLflow GenAI metrics (make_genai_metric)
Part 3  Deterministic, LLM-free checks (AST, anchors, lint, ROUGE-L, MAE)
Part 4  Hybrid eval frame + mlflow.evaluate() orchestration
Part 5  Meta-evaluation: judge-vs-human agreement (kappa, rho, alpha, ICC)
Part 6  Bias mitigation: pairwise comparison with position-swap debiasing
Part 7  Robustness: self-consistency and perturbation probes
Part 8  Statistical inference: bootstrap CIs, paired tests, multiplicity
Part 9  Artifacts: radar, confusion matrix, error taxonomy, judge card
Part 10 CLI plus a stub judge so the pipeline is testable without a GPU

Two MLflow landmines this module deliberately works around
----------------------------------------------------------
1. ``make_genai_metric`` renders its prompt through
   ``mlflow.metrics.genai.prompt_template.PromptTemplate``, which calls
   ``str.format`` on the *already-substituted* template. A literal brace
   anywhere in ``definition``, ``grading_prompt`` or an ``EvaluationExample``
   therefore becomes a format placeholder, no kwarg matches it, and
   PromptTemplate silently drops the whole template string -- the judge is
   sent an EMPTY prompt and every score comes back ``None``, with no warning.
   ``_assert_brace_free`` turns that into a load-time error instead of a
   silent run of null results. (Per-row values -- the prediction, the bundle,
   the gold reference -- are substituted as kwargs and are safe; only
   template-time text is not.)

2. Chain-of-thought cannot be enforced inside a single judge completion.
   BOTH ``make_genai_metric`` and ``make_genai_metric_from_prompt`` append
   their own trailing instruction ("return score, then justification, in two
   lines") AFTER the caller's rubric, and recency wins: a local judge obeys
   the library's closing instruction and emits the score token first, so any
   "reasoning" is written after the number and can only rationalise it. This
   was measured, not assumed -- see ``COT_PROTOCOL``.

   The fix is ``cot_mode="two_stage"`` (the default). A separate reasoning
   call produces the evidence scan and the per-test anchor check with NO
   score field available to it; that text is then passed into the scoring
   call as an extra grading-context column. The score is therefore genuinely
   conditioned on written reasoning, and because the reasoning was committed
   in an earlier completion it cannot be bent to fit a number already
   chosen. This is strictly stronger than in-completion CoT, and it costs one
   extra judge call per row per metric. ``cot_mode="inline"`` keeps the
   single-call behaviour for cheap runs, and documents its own weakness.

What this adds to the existing implementation
---------------------------------------------
This module EXTENDS the two judge/eval pipelines already in the repo; it does
not replace either. Part 11 holds the seams. Reused as-is, never reimplemented:
``research.eval.metrics.summarise_example`` (base row), ``analysis
.paired_bootstrap_diff`` (CI), ``judges.code_based_scorer
.numeric_grade_accuracy`` (grade error), ``judges.trace_adapters
.read_candidate`` (trace reading), ``llmops.mlflow_config`` (tracking),
``llmops.prompt_registry`` (rubric versioning), and
``judges.citation_ground_custom_judge`` (per-claim LLM grounding).

Gaps in the current implementation that this closes:

1. One judge dimension became five. ``custom_llm_judge`` emits
   ``citation_hallucination_rate`` and ``actionable_and_targeted_rate`` --
   both binary-derived rates with no written scale. A model can be perfectly
   grounded and still give useless advice, or reason invalidly from real
   evidence; those are different risks and a rate cannot separate them.
2. Rubrics had no anchors. The existing judge prompt says "judge if
   RAW_BUNDLE supports each citation" with no definition of what each score
   level means, so scores are not reproducible across judge models or
   prompt edits. Every dimension here carries written 1-5 band anchors, a
   numbered test list, and a ``rubric_hash`` logged as an MLflow param.
3. No few-shot calibration. Local judges collapse onto the middle of a scale
   without exemplars; each metric now ships a high and a low exemplar drawn
   from this project's own domain.
4. Reasoning came after the score, or not at all. See note (2) below -- and
   note that the existing ``JUDGE_SYSTEM_PROMPT`` asks for a JudgeVerdict
   whose reasoning fields are populated per item but whose rates are derived
   afterwards, so nothing forces reasoning to precede judgement.
5. The judge was never validated. There was no agreement measurement of any
   kind, so the existing rates are unfalsifiable: a judge agreeing with
   nobody still produces a tidy mean. Part 5 adds kappa, weighted kappa,
   rho, tau, alpha, ICC and a bias term, each with a bootstrap CI and an n.
6. No bias measurement. Position bias, verbosity bias and self-preference
   bias were all unmeasured and unmentioned. Parts 6 and 7 measure the first
   two; ``assert_judge_independence`` refuses to run the third by default --
   relevant here because a judge drawn from the same model family as the
   candidates would grade its own family.
7. No consistency measurement. ``LLM_TEMPERATURE`` defaults to 0 and is
   assumed to make the judge deterministic; Part 7 measures whether it does.
8. Statistics without inference. ``analysis.py`` computes a bootstrap CI but
   no significance test, no effect size, and no multiplicity correction
   across the 15+ comparisons a 3-model x 5-metric sweep produces. Part 8
   adds Wilcoxon, Cliff's delta, Holm/BH -- and ``min_attainable_p``, which
   makes explicit that at n=5 the test CANNOT reach p<=0.05 at any effect
   size, so "not significant" there means nothing.
9. The judge hand-off was never wired up. ``summarise_example`` has always
   emitted a ``judge_quality_score=None`` placeholder and
   ``attach_judge_scores.py`` has always been ready to fill it; nothing ever
   produced the CSV. ``export_judge_scores`` does.
10. No artifacts and no stakeholder-facing summary. ``judge_card`` is a
    datasheet stating what the judge is, how far it agrees with humans, how
    biased it is, and what it may not be used for.
11. Untestable without a GPU. ``install_stub_judge`` lets the whole pipeline
    run in CI, and ``selftest`` asserts known-answer invariants on a
    synthetic set where the degraded candidate must score worse.

Two defects found while integrating, fixed outside this file:
  * ``schemas/rubrics_dimension_score._normalize_citation`` stringified an
    already-valid ``EvidenceCitation``, dropping ``reason`` and making
    ``schemas/benchmark.py`` -- the gold reference data -- raise on import.
    Nothing imported it, so it had been dead.
  * ``judges/custom_llm_judge.py`` defaults its judge to
    ``sprintsight-judge-phi``, and ``judges/run_judges.py`` hardcodes trace
    ids in ``__main__``; neither is pulled or valid in this checkout.

Usage
-----
    # Offline self-test of the entire pipeline (no model server needed):
    python -m research.eval.mlflow_judge_eval selftest

    # Real run against local Ollama:
    python -m research.eval.mlflow_judge_eval evaluate --judge-model phi4:14b
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import math
import os
import random
import re
import sys
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, Literal

import mlflow
import numpy as np
import pandas as pd
from mlflow.metrics import make_metric
from mlflow.metrics.base import MetricValue
from mlflow.metrics.genai import EvaluationExample, make_genai_metric
from mlflow.metrics.genai.prompts.v1 import EvaluationModel

from judges.code_based_scorer import numeric_grade_accuracy
from llmops.mlflow_config import configure_mlflow, get_experiment_id
from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from research.eval.analysis import paired_bootstrap_diff
from research.eval.metrics import summarise_example
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment

log = logging.getLogger(__name__)

__all__ = [
    "JUDGE_METRIC_SPECS",
    "CalibrationReport",
    "JudgeRecord",
    "build_deterministic_metrics",
    "build_eval_frame",
    "build_genai_metrics",
    "configure_judge_endpoint",
    "evaluate_judge_calibration",
    "install_stub_judge",
    "judge_card",
    "model_comparison_report",
    "pairwise_tournament",
    "run_judge_evaluation",
    "self_consistency_probe",
]


# =============================================================================
# Part 0 -- Judge endpoint configuration
# =============================================================================

# The 1-5 scale is used for every LLM-judged dimension. It is deliberately
# coarser than the 1-10 scale the candidate models grade students on: a judge
# asked to discriminate ten levels of "faithfulness" produces noise, and the
# meta-evaluation in Part 5 needs enough mass per cell for a kappa to mean
# anything. Five ordered levels with written anchors is the standard
# compromise in the rubric-design literature.
RUBRIC_MIN = 1
RUBRIC_MAX = 5

JUDGE_EXPERIMENT = os.getenv("SPRINTSIGHT_JUDGE_EXPERIMENT", "sprintsight-judge-eval")

# The judge MUST come from a different model family than the candidates
# under test (models/Modelfile.*, schemas/modelname.py); otherwise a judge
# grading its own family introduces self-preference bias -- a judge's measured
# tendency to prefer text from its own family -- that becomes indistinguishable
# from real quality.
#
# phi4:14b is the default because the existing judge code already reaches for
# the phi family (`SPRINTSIGHT_JUDGE_MODEL` defaults to "sprintsight-judge-phi"
# in judges/custom_llm_judge.py), it is not a llama derivative, and at Q4 it
# fits alongside a 3B candidate on a 24 GB card. `assert_judge_independence`
# enforces the family rule at run time rather than trusting this default.
#
#   ollama pull phi4:14b          # ~9 GB, recommended
#   ollama pull qwen2.5:14b-instruct   # alternative, also non-llama
DEFAULT_JUDGE_MODEL = os.getenv("SPRINTSIGHT_JUDGE_MODEL", "phi4:14b")

# Opt-out for the family rule. Exists because a reviewer may legitimately want
# to MEASURE self-preference bias by deliberately judging within a family;
# it is not there to make a convenient judge acceptable.
ALLOW_SAME_FAMILY_JUDGE = os.getenv("SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE", "") == "1"

# Greedy decoding plus a fixed seed: the judge is an instrument, and an
# instrument that gives a different reading each time it is used cannot
# calibrate anything. Part 7 then deliberately breaks this in order to
# MEASURE how much of our signal depends on it.
JUDGE_SEED = int(os.getenv("SPRINTSIGHT_JUDGE_SEED", "7"))

# max_tokens must sit far above MLflow's 200-token default: the CoT protocol
# asks for an evidence scan and a per-test anchor check before the score, and
# a truncated response loses the score field entirely.
JUDGE_MAX_TOKENS = int(os.getenv("SPRINTSIGHT_JUDGE_MAX_TOKENS", "1200"))

# How much of the candidate's evidence view to show the judge.
#
# 32000 chars is roughly 8k tokens, which leaves room alongside the rubric,
# the few-shot exemplars and the stage-one audit inside a 16k-context judge
# such as phi4:14b. It is sized against what has to fit: the union of
# per-dimension commit samples measured 64-89 commits on the real sprints,
# which renders at well under this, so truncation should be the exception
# rather than the rule.
#
# Raising this is NOT the way to fix a truncated bundle -- the full real-sprint
# bundle renders at up to 2.4 MB, so no budget makes it fit. The fix is to show
# the candidate's sampled view instead; see candidate_visible_commits.
JUDGE_BUNDLE_CHAR_BUDGET = int(os.getenv("SPRINTSIGHT_JUDGE_BUNDLE_CHARS", "32000"))


# Context window requested of the judge, as Ollama's `options.num_ctx`.
#
# This must be set explicitly. Ollama applies its own small default (a few
# thousand tokens) unless a Modelfile or the request says otherwise, and it
# truncates an over-long prompt SILENTLY -- no error, no warning. Every
# character budget in this module would be meaningless if the server quietly
# dropped the end of the bundle, and the symptom would be the judge calling
# real citations fabricated: exactly the bug candidate_visible_commits exists
# to fix. llm_client.py takes the same precaution via _request_extra_body.
#
# 32768 covers the 32000-char bundle budget plus the rubric, the exemplars
# and the stage-one audit with room to spare (chars // 4 is the usual rough
# token estimate). Keep it at or below the judge's real ceiling: phi4:14b is
# 16k, qwen2.5:14b-instruct is 32k. Set SPRINTSIGHT_JUDGE_NUM_CTX to 16384
# for a 16k judge, or 0 to omit the override entirely and let Ollama decide.
JUDGE_NUM_CTX = int(os.getenv("SPRINTSIGHT_JUDGE_NUM_CTX", "32768"))


def judge_parameters(temperature: float = 0.0, seed: int | None = None) -> dict[str, Any]:
    """Decoding parameters forwarded verbatim to the judge's chat endpoint.

    ``response_format`` is included because local models wrap JSON in
    markdown fences often enough to matter, and a fenced response fails both
    of MLflow's parse paths. Ollama honours OpenAI's ``json_object`` mode, and
    MLflow passes unrecognised parameters straight through to the payload --
    verified for both ``response_format`` and ``options``.
    """
    parameters: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": JUDGE_MAX_TOKENS,
        "top_p": 1.0,
        "seed": JUDGE_SEED if seed is None else seed,
        "response_format": {"type": "json_object"},
    }
    if JUDGE_NUM_CTX > 0:
        parameters["options"] = {"num_ctx": JUDGE_NUM_CTX}
    return parameters


def configure_judge_endpoint(
    judge_model: str = DEFAULT_JUDGE_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Point MLflow's ``openai:/`` provider at local Ollama; return the URI.

    MLflow resolves ``openai:/<model>`` through its gateway OpenAIProvider,
    which reads ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` from the environment.
    Ollama's ``/v1`` endpoint is OpenAI-compatible, so setting those two
    variables is the entire integration: no deployment server, no gateway
    config file, and the judge weights stay on hardware we control -- which
    is also what lets a reader reproduce the study.

    Call before ``mlflow.evaluate``. The provider is constructed per call, so
    a later change to these variables is picked up.
    """
    resolved_base = base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    if not resolved_base.rstrip("/").endswith("/v1"):
        resolved_base = resolved_base.rstrip("/") + "/v1"
    os.environ["OPENAI_API_BASE"] = resolved_base
    # Ollama ignores the key, but the OpenAI wire format requires one.
    os.environ["OPENAI_API_KEY"] = api_key or os.getenv("OLLAMA_API_KEY") or "ollama"
    uri = f"openai:/{judge_model}"
    log.info("Judge endpoint configured: %s via %s", uri, resolved_base)
    return uri


_BRACE = re.compile(r"[{}]")


def _assert_brace_free(text: str, where: str) -> str:
    """Reject template-time text containing braces. See module docstring (1).

    Not defensive paranoia about a hypothetical: one brace here produces an
    empty judge prompt and a full column of None scores that looks exactly
    like "the judge could not parse the output", which is the hardest class
    of bug to notice in an eval pipeline.
    """
    if _BRACE.search(text):
        raise ValueError(
            f"{where} contains a literal brace. MLflow's PromptTemplate would "
            "treat it as a format placeholder and silently emit an EMPTY judge "
            "prompt, so every score would come back None. Rewrite the text "
            "without braces -- describe JSON keys in prose instead."
        )
    return text


def _strip_braces(text: str) -> str:
    """Sanitise rendered text that will be embedded at template time."""
    return _BRACE.sub("", text)


# =============================================================================
# Part 1 -- Chain-of-thought protocol, rubric anchors, few-shot calibration
# =============================================================================

# Requested reasoning format for the SCORING call. We ask for a JSON object
# with the reasoning keys first, which MLflow's parser accepts because it
# tries json.loads before its score-first regex.
#
# Measured caveat: this request is NOT reliably honoured. MLflow appends its
# own "score, then justification" instruction after this rubric, and a local
# 3B-8B judge follows the closing instruction -- observed output was
# {"score": 5, "justification": ...}, i.e. the number first. In-completion
# CoT is therefore requested but never relied upon; the real guarantee comes
# from the two-stage reasoning pass below (ANALYSIS_PROTOCOL), whose output
# is injected as grading context so the score is conditioned on reasoning
# that was already committed to text.
COT_PROTOCOL = _assert_brace_free(
    """
Reasoning protocol -- follow it exactly:

Reply with a single JSON object and nothing else. Emit its keys in EXACTLY
this order, so that all of your reasoning is written down before you commit
to a number:

  1. key "evidence_scan" -- an array of 2 to 5 short strings. Each string
     names one concrete item you actually checked and what you found: a
     commit SHA, a Jira ticket key, a filename, a peer-review comment, or a
     numeric claim you either verified or could not verify.
  2. key "anchor_check" -- one string. Walk the numbered rubric tests below
     in order and state for each whether it PASSED or FAILED, and on what
     evidence. Use the form T1 PASSED because ..., T2 FAILED because ...
  3. key "justification" -- two to four sentences explaining which score band
     the evidence places this output in, referring to the anchors by their
     wording rather than by number alone.
  4. key "score" -- a single integer from 1 to 5, and nothing else.

Hard rules:
- Never write the score key before the three reasoning keys.
- Never wrap the JSON in code fences and never add prose outside the object.
- Judge only the output in front of you. Do not reward length, confidence or
  polished writing: a short output citing real evidence outranks a long one
  that does not.
- If the output is empty or unparseable, score 1 and say so.
""",
    "COT_PROTOCOL",
)


def _render_anchors(anchors: Mapping[int, str]) -> str:
    """Render 1-5 score anchors as brace-free prose, highest band first."""
    lines = [
        ("Score anchors -- choose the single highest band whose description is "
        "fully true of the output:")
    ]
    for level in sorted(anchors, reverse=True):
        lines.append(f"- Score {level}: {' '.join(anchors[level].split())}")
    return "\n".join(lines)


def _render_tests(tests: Sequence[str]) -> str:
    lines = ["Rubric tests -- answer every one of these in anchor_check:"]
    for index, test in enumerate(tests, start=1):
        lines.append(f"- T{index}: {' '.join(test.split())}")
    return "\n".join(lines)


@dataclass(frozen=True)
class JudgeMetricSpec:
    """One LLM-judged dimension, assembled into a native MLflow GenAI metric.

    Keeping the rubric as data rather than as a formatted blob means the
    anchors can be hashed for provenance (``rubric_hash``), diffed in review,
    and reused verbatim by the self-consistency probe in Part 7 -- which must
    send the *same* prompt as ``mlflow.evaluate`` or it measures nothing.
    """

    name: str
    definition: str
    tests: tuple[str, ...]
    anchors: Mapping[int, str]
    grading_context_columns: tuple[str, ...]
    examples: tuple[EvaluationExample, ...] = ()
    greater_is_better: bool = True

    def grading_prompt(self) -> str:
        return _assert_brace_free(
            "\n\n".join([
                _render_tests(self.tests),
                _render_anchors(self.anchors),
                COT_PROTOCOL.strip(),
            ]),
            f"grading_prompt for {self.name}",
        )

    def analysis_prompt(
        self, *, prediction: str, grading_context: Mapping[str, str]
    ) -> str:
        """Stage-one prompt: reasoning only, with no score field available.

        Built by hand rather than through MLflow, precisely because MLflow
        appends a "return a score" instruction to everything it renders --
        which is the behaviour this stage exists to escape. Withholding the
        score field is the whole mechanism: the judge cannot pick a number
        and work backwards if it has not been asked for a number yet.
        """
        context = "\n\n".join(
            f"{key.upper()}:\n{value}" for key, value in grading_context.items()
        )
        return "\n".join([
            ("You are auditing one dimension of an AI-generated software "
            "engineering sprint assessment. Do NOT award a score. Do NOT say "
            "whether the output is good or bad overall. Your only job is to "
            "establish the facts another evaluator will score from."),
            "",
            f"DIMENSION UNDER AUDIT: {self.name}",
            f"WHAT THIS DIMENSION MEANS:\n{self.definition}",
            "",
            _render_tests(self.tests),
            "",
            context,
            "",
            f"ASSESSMENT UNDER AUDIT:\n{prediction}",
            "",
            "Reply with a single JSON object and nothing else, with these keys:",
            ('  "evidence_scan": an array of 2 to 5 strings, each naming one '
            "concrete item you checked (a commit SHA, a ticket key, a "
            "filename, a named metric, a person) and what you found when you "
            "looked for it in the ground-truth material above."),
            ('  "anchor_check": an array with one string per rubric test, in '
            "order, each of the form T1 PASSED because ... or T1 FAILED "
            "because ... citing the specific evidence."),
            ('  "unresolved": an array of strings naming anything you could not '
            "verify either way, or an empty array. Do not guess."),
            "",
            ("Report only what you can check. An empty or unparseable "
            "assessment is a finding, not an error: say so in evidence_scan."),
        ])

    def rubric_hash(self) -> str:
        """Stable hash of the full rubric text, logged as an MLflow param.

        A judge score is only comparable across runs if the rubric that
        produced it was identical. Version strings get forgotten; a hash of
        the actual text does not.
        """
        hasher = hashlib.sha256()
        hasher.update(self.name.encode())
        hasher.update(self.definition.encode())
        hasher.update(self.grading_prompt().encode())
        for example in self.examples:
            hasher.update(str(example).encode())
        return hasher.hexdigest()[:16]

    def eval_prompt_for(
        self,
        *,
        judge_uri: str,
        prediction: str,
        inputs: str,
        grading_context: Mapping[str, str],
        parameters: Mapping[str, Any] | None = None,
    ) -> str:
        """The exact payload ``mlflow.evaluate`` would send for one row.

        Built through MLflow's own ``EvaluationModel`` rather than a
        hand-rolled copy, so Parts 6 and 7 cannot drift away from what the
        headline numbers were produced with.
        """
        model = EvaluationModel(
            name=self.name,
            definition=self.definition,
            grading_prompt=self.grading_prompt(),
            examples=list(self.examples),
            model=judge_uri,
            parameters=dict(parameters or judge_parameters()),
            include_input=True,
        )
        context_lines = "\n".join(
            f"key: {key}\nvalue:\n{value}" for key, value in grading_context.items()
        )
        rendered = model.to_dict()["eval_prompt"].format(
            input=inputs, output=prediction, grading_context_columns=context_lines
        )
        if not rendered.strip():
            raise RuntimeError(
                f"Rendered an empty judge prompt for metric '{self.name}'. This is "
                "the PromptTemplate brace failure described in the module docstring."
            )
        return rendered

    def cot_column(self) -> str:
        """Name of the frame column holding this metric's stage-one analysis."""
        return f"cot_{self.name}"

    def _example_context(self, example: EvaluationExample) -> dict[str, str]:
        """An exemplar's grading context as a dict, whatever form it was given in.

        ``EvaluationExample.grading_context`` is typed ``dict | str | None``.
        A bare string is legal and MLflow renders it as one unlabelled blob,
        so it has to be mapped onto a named column before the two-stage path
        can add its own -- otherwise building the metric raises on the
        dict unpacking, at import time, for an example that was perfectly
        valid in single-stage mode.
        """
        context = example.grading_context
        if isinstance(context, dict):
            return dict(context)
        if isinstance(context, str):
            first = (
                self.grading_context_columns[0]
                if self.grading_context_columns
                else "grading_context"
            )
            return {first: context}
        return {}

    def build(
        self, judge_uri: str, *, max_workers: int = 1, two_stage: bool = False
    ) -> Any:
        _assert_brace_free(self.definition, f"definition for {self.name}")
        grading_prompt = self.grading_prompt()
        context_columns = list(self.grading_context_columns)
        examples = list(self.examples)

        if two_stage:
            context_columns.append(self.cot_column())
            grading_prompt = _assert_brace_free(
                "A PRIOR EVIDENCE AUDIT of this output has already been "
                f"carried out and is supplied above as {self.cot_column()}. "
                "Treat its findings as established. Score the band its "
                "anchor_check results place this output in, and say in your "
                "justification which of its findings decided the band. If the "
                "audit reports a test FAILED, you may not award a band whose "
                "anchor requires that test to pass.\n\n" + grading_prompt,
                f"two-stage grading_prompt for {self.name}",
            )
            # MLflow validates that every example carries every grading
            # context column. The exemplar justifications already ARE anchor
            # checks, so reusing them keeps the few-shot demonstrations
            # consistent with what the judge will actually be shown.
            examples = [
                EvaluationExample(
                    output=example.output,
                    score=example.score,
                    justification=example.justification,
                    input=example.input,
                    grading_context={
                        **self._example_context(example),
                        self.cot_column(): example.justification,
                    },
                )
                for example in examples
            ]

        for index, example in enumerate(examples):
            _assert_brace_free(str(example), f"example {index} for {self.name}")
        return make_genai_metric(
            name=self.name,
            definition=self.definition,
            grading_prompt=grading_prompt,
            examples=examples,
            version="v1",
            model=judge_uri,
            grading_context_columns=context_columns,
            include_input=True,
            parameters=judge_parameters(),
            aggregations=["mean", "variance", "p90"],
            greater_is_better=self.greater_is_better,
            # One worker by default: these judges run against a single local
            # Ollama server, and MLflow's default of 10 concurrent requests
            # makes it thrash between loaded models instead of going faster.
            max_workers=max_workers,
            metric_metadata={"rubric_hash": self.rubric_hash(), "scale": "1-5"},
        )


# =============================================================================
# Part 2 -- The five native MLflow GenAI metrics
# =============================================================================
#
# Why five and not one "overall quality" judge: a single scalar cannot
# separate the two failure modes that matter to a grading tool. A model can
# be perfectly faithful to the evidence and still give useless advice, or
# give excellent advice built on a fabricated commit. Collapsing those into
# one number means a stakeholder cannot tell which risk they are carrying.
# Each metric below is also chosen to be judgeable: it asks the judge to
# verify something present in the evidence, never to guess a latent "quality".
#
# Deliberately NOT judged by an LLM (handled arithmetically in Part 3):
# numeric grade accuracy against gold, and cross-fixture rank ordering.
# Asking a 3B model to compare two integers adds latency and a second error
# source to something `abs(a - b)` does exactly.

# -- Few-shot calibration examples -------------------------------------------
#
# Each metric gets one HIGH and one LOW exemplar. Two is a deliberate floor:
# few-shot examples are what stop a local judge collapsing onto the middle of
# the scale, but each one is also prompt budget spent before the real output
# is read, and more than two or three measurably crowds out the bundle on a
# 4k-context judge. The exemplars are written in the project's own domain
# (AUTH-* tickets, real commit-shaped SHAs) so the judge calibrates on inputs
# shaped like the ones it will see. All text is brace-free -- see Part 0.

_FAITHFULNESS_HIGH = EvaluationExample(
    input="Grade the testing dimension for team CS203-G6, sprint S1.",
    output=(
        "testing scored 8 of 10. Justification: testing was planned as its own "
        "ticket and delivered alongside the feature it covers. Evidence: Jira "
        "ticket AUTH-2 titled Auth Tests is marked Done and assigned to Bob; "
        "commit 4f21ab9 by Bob added 120 lines to tests/test_auth.py."
    ),
    score=5,
    justification=(
        "T1 PASSED: both identifiers, AUTH-2 and 4f21ab9, appear in the bundle. "
        "T2 PASSED: the 120-line figure and the Done status match the bundle "
        "exactly. T3 PASSED: Bob is a commit author and the ticket assignee. "
        "T4 PASSED: no tool or file outside the bundle is claimed. Every "
        "factual claim is traceable, which is the top band."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, message Write unit tests for auth, plus "
            "120 lines minus 0, files tests/test_auth.py. jira_tickets: AUTH-2 "
            "Auth Tests, status Done, assignee Bob, story_points 3."
        )
    },
)

_FAITHFULNESS_LOW = EvaluationExample(
    input="Grade the cicd dimension for team CS203-G6, sprint S1.",
    output=(
        "cicd scored 7 of 10. Justification: the team maintains a mature "
        "deployment pipeline with automated rollback. Evidence: commit 9c0d7e1 "
        "configured the GitHub Actions release workflow; Jenkinsfile defines "
        "the staging promotion gate."
    ),
    score=1,
    justification=(
        "T1 FAILED: neither 9c0d7e1 nor Jenkinsfile appears anywhere in the "
        "bundle, which contains no CI configuration at all. T2 FAILED: there "
        "is no evidence of a pipeline to quantify. T4 FAILED: automated "
        "rollback and a staging gate are inventions. The central claims are "
        "fabricated, so this is the bottom band regardless of how confident "
        "the prose sounds."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, files tests/test_auth.py; 1a2b3c4 by "
            "Alice, files src/auth.py. jira_tickets: AUTH-2 Auth Tests, Done. "
            "artifact_metrics: none. No workflow, Dockerfile or CI file present."
        )
    },
)

_ACTIONABILITY_HIGH = EvaluationExample(
    input="Review the recommendations for team CS203-JY, sprint S2.",
    output=(
        "Recommendations: 1. Assign Dana to add integration tests for the "
        "payment handler in src/payments.py, which AUTH-7 left untested. "
        "2. Split the 900-line commit 7de45f2 into reviewable units before the "
        "next sprint review."
    ),
    score=5,
    justification=(
        "T1 PASSED: both recommendations name a file and an owner or a specific "
        "commit. T2 PASSED: both are completable inside one sprint. T3 PASSED: "
        "testing at 3 and code_quality at 4 are the two lowest dimensions in "
        "the gold reference, and the recommendations target exactly those. "
        "T4 PASSED: neither action is already done in the bundle. Concrete, "
        "assignable and aimed at the real bottleneck."
    ),
    grading_context={
        "gold_reference": (
            "rubric scores out of 10: testing 3, code_quality 4, documentation "
            "7, requirements 8, collaboration 8, cicd 6. Lowest two dimensions "
            "are testing and code_quality."
        ),
        "artifact_bundle": (
            "commits: 7de45f2 by Dana, plus 900 lines minus 12, files "
            "src/payments.py. jira_tickets: AUTH-7 Payment handler, status Done, "
            "assignee Dana. artifact_metrics: no coverage key present."
        ),
    },
)

_ACTIONABILITY_LOW = EvaluationExample(
    input="Review the recommendations for team CS203-JY, sprint S2.",
    output=(
        "Recommendations: 1. Keep up the great communication. 2. Continue to "
        "improve code quality going forward. 3. Maintain the strong "
        "requirements tracking the team has shown."
    ),
    score=1,
    justification=(
        "T1 FAILED: no file, ticket or owner is named in any of the three. "
        "T2 FAILED: continue and maintain are not assignable actions. "
        "T3 FAILED: two of the three praise collaboration and requirements, "
        "the team's two STRONGEST dimensions in gold, while testing at 3 is "
        "never mentioned. This is generic filler, the bottom band."
    ),
    grading_context={
        "gold_reference": (
            "rubric scores out of 10: testing 3, code_quality 4, documentation "
            "7, requirements 8, collaboration 8, cicd 6. Lowest two dimensions "
            "are testing and code_quality."
        ),
        "artifact_bundle": (
            "commits: 7de45f2 by Dana, files src/payments.py. jira_tickets: "
            "AUTH-7 Payment handler, status Done. peer_evaluations: 3 entries."
        ),
    },
)

_CORRECTNESS_HIGH = EvaluationExample(
    input="Check the technical reasoning for the testing dimension.",
    output=(
        "testing scored 4 of 10. A test file exists, tests/test_auth.py with "
        "120 lines added in 4f21ab9, but the bundle reports no coverage "
        "metric, so the presence of tests cannot be read as the code being "
        "covered. Scored on demonstrated test work only."
    ),
    score=5,
    justification=(
        "T2 PASSED and is the whole point: the output explicitly refuses to "
        "infer coverage from the existence of a test file, and says so. "
        "T1 PASSED: the 120 lines are reported as volume of test work, not as "
        "evidence of quality. T3 and T4 are not engaged. Every inference from "
        "evidence to judgement is valid."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 4f21ab9 by Bob, plus 120 lines, files tests/test_auth.py. "
            "artifact_metrics: no coverage key present."
        ),
        "gold_reference": "Human reference: testing 4 of 10.",
    },
)

_CORRECTNESS_LOW = EvaluationExample(
    input="Check the technical reasoning for the code_quality dimension.",
    output=(
        "code_quality scored 9 of 10. The team added 4,200 lines this sprint, "
        "far above average, and the CI workflow file proves the test suite is "
        "green. AUTH-9 is marked Done so the refactor is merged and in "
        "production."
    ),
    score=1,
    justification=(
        "T1 FAILED: 4,200 added lines is used directly as a quality proxy, "
        "when high churn is at least as consistent with copied or generated "
        "code. T3 FAILED: the presence of a workflow FILE is treated as proof "
        "the suite passes, which it cannot establish. T4 FAILED: a Done ticket "
        "is conflated with merged and deployed code. Three invalid inferences, "
        "and the conclusion does not follow from the cited evidence."
    ),
    grading_context={
        "artifact_bundle": (
            "commits: 8 commits by 2 authors, plus 4200 lines minus 60. "
            "jira_tickets: AUTH-9 Refactor auth, status Done. artifact_metrics: "
            "no test result or coverage key present."
        ),
        "gold_reference": "Human reference: code_quality 5 of 10.",
    },
)

_SPECIFICITY_HIGH = EvaluationExample(
    input="Check evidence specificity across all six dimensions.",
    output=(
        "code_quality cites 1a2b3c4 in src/auth.py. testing cites AUTH-2 and "
        "tests/test_auth.py. documentation cites AUTH-5 and docs/auth.md. "
        "requirements cites 8 of 10 story points Done. collaboration cites "
        "Bob's peer review of Alice. cicd cites the absent coverage metric."
    ),
    score=5,
    justification=(
        "T1 PASSED: all six dimensions carry a hard anchor, a SHA, a ticket "
        "key, a file path or a named metric. T2 PASSED: each anchor is tied to "
        "the dimension it is cited for in one sentence. Top band."
    ),
    grading_context={"artifact_bundle": "All cited SHAs, tickets and files are present."},
)

_SPECIFICITY_LOW = EvaluationExample(
    input="Check evidence specificity across all six dimensions.",
    output=(
        "The team made several good commits and the tickets were mostly "
        "completed. Documentation was adequate. Collaboration was strong "
        "based on the peer feedback. CI looked reasonable."
    ),
    score=1,
    justification=(
        "T1 FAILED: not one commit SHA, ticket key, filename or metric name "
        "appears. Several, mostly and reasonable are unverifiable quantifiers. "
        "T2 FAILED: nothing is tied to a dimension by evidence. No hard "
        "anchors anywhere, the bottom band."
    ),
    grading_context={"artifact_bundle": "Bundle contains 8 commits and 10 tickets with keys."},
)

_ADHERENCE_HIGH = EvaluationExample(
    input="Check whether the numeric score matches the published rubric band.",
    output=(
        "requirements scored 7 of 10. 8 of 10 assigned tickets are Done, 21 of "
        "26 story points completed, none abandoned or blocked."
    ),
    score=5,
    justification=(
        "T1 PASSED: the published band for 6 to 8 is most tickets Done with "
        "none abandoned or stuck, and 8 of 10 Done with zero blocked sits "
        "squarely inside it. T2 PASSED: the narrative supports the number "
        "without inflating it, and gold also records 7. No drift."
    ),
    grading_context={
        "rubric_criteria": (
            "requirements band 9 to 10: all tickets Done and high story points. "
            "Band 6 to 8: most tickets Done, none abandoned or stuck. Band 3 to "
            "5: fewer than half Done. Band 1 to 2: little or no progress."
        ),
        "gold_reference": "requirements 7 of 10.",
    },
)

_ADHERENCE_LOW = EvaluationExample(
    input="Check whether the numeric score matches the published rubric band.",
    output=(
        "requirements scored 9 of 10. The team showed excellent commitment and "
        "a positive attitude. 3 of 10 tickets are Done and two are Blocked."
    ),
    score=1,
    justification=(
        "T1 FAILED: 3 of 10 Done with two Blocked falls in the published 3 to 5 "
        "band, fewer than half Done, yet the output awards 9. T2 FAILED: the "
        "stated reason, commitment and attitude, is not a rubric criterion for "
        "this dimension. The score is inflated by two whole bands on "
        "non-rubric grounds, the bottom band."
    ),
    grading_context={
        "rubric_criteria": (
            "requirements band 9 to 10: all tickets Done and high story points. "
            "Band 6 to 8: most tickets Done, none abandoned or stuck. Band 3 to "
            "5: fewer than half Done. Band 1 to 2: little or no progress."
        ),
        "gold_reference": "requirements 4 of 10.",
    },
)


CODE_FAITHFULNESS = JudgeMetricSpec(
    name="Code_Faithfulness",
    definition=(
        "Code faithfulness measures whether every factual claim the assessment "
        "makes about the team's software artifacts can be traced back to the "
        "artifact bundle it was given. The bundle of real commits, Jira tickets "
        "and peer evaluations is the only ground truth. A claim is unfaithful "
        "if its identifier does not exist in the bundle, if a verifiable "
        "attribute of that identifier is wrong, such as the author, the line "
        "count, the status or the filename, or if it describes work, tooling or "
        "files the bundle does not contain. Confident, fluent prose about "
        "artifacts that are not there is the most damaging failure a grading "
        "tool can have, so it scores at the bottom of this scale."
    ),
    tests=(
        ("Every citation identifier, commit SHA, ticket key, filename or metric "
        "name, appears in the artifact bundle."),
        ("Every number quoted, line counts, ticket counts, story points, "
        "percentages, matches the bundle."),
        ("Every person named appears in the bundle as a commit author, a ticket "
        "assignee or a peer reviewer."),
        ("No file, tool, pipeline or process is described that the bundle does "
        "not contain."),
    ),
    anchors={
        5: "Every factual claim is traceable. Each citation identifier appears "
           "in the bundle and each verifiable attribute of it is correct.",
        4: "Every citation resolves to a real bundle item and all attributes are "
           "correct, but at most one non-citation claim is a mild overstatement "
           "of what the evidence shows.",
        3: "All citation identifiers exist, but at least one misattributes a "
           "verifiable attribute, naming the wrong author, count, status or file.",
        2: "At least one citation identifier cannot be found in the bundle at "
           "all, or several attributes across the output are wrong.",
        1: "Central claims are fabricated. The narrative describes commits, "
           "files, tooling or work the bundle does not contain.",
    },
    grading_context_columns=("artifact_bundle",),
    examples=(_FAITHFULNESS_HIGH, _FAITHFULNESS_LOW),
)


BUG_ACTIONABILITY = JudgeMetricSpec(
    name="Bug_Actionability",
    definition=(
        "Bug actionability measures whether the weaknesses and recommendations "
        "in the assessment give the student team something they can actually "
        "do next, aimed at the problem that is actually holding them back. An "
        "actionable item names a concrete artifact, a file, a ticket, a commit "
        "or a named person, and a verb a team member could be assigned this "
        "week. A targeted item addresses one of the dimensions the gold "
        "reference scores lowest, rather than praising a dimension that was "
        "already strong. Generic encouragement such as communicate better or "
        "keep improving code quality is the characteristic failure here: it "
        "reads as feedback while carrying no information."
    ),
    tests=(
        ("Each recommendation names a concrete artifact or an owner, not just a "
        "dimension or a virtue."),
        ("Each recommendation uses a verb that could be assigned to one person "
        "and completed within a single sprint."),
        ("The recommendations address at least one of the two lowest-scoring "
        "dimensions in the gold reference."),
        ("No recommendation asks for work the artifact bundle shows is already "
        "finished."),
    ),
    anchors={
        5: "Every recommendation names a specific artifact or owner with an "
           "assignable next step, and the set targets the gold reference's "
           "lowest-scoring dimensions.",
        4: "Recommendations are concrete and assignable, but at least one aims "
           "at a dimension that was already strong.",
        3: "A mix of concrete and generic items. The true bottleneck is "
           "mentioned, but the action proposed for it is vague.",
        2: "Mostly generic advice with no named artifact or owner, and no clear "
           "link to the weakest dimension.",
        1: "No actionable content at all, or it recommends work the bundle "
           "shows is already complete.",
    },
    grading_context_columns=("gold_reference", "artifact_bundle"),
    examples=(_ACTIONABILITY_HIGH, _ACTIONABILITY_LOW),
)


TECHNICAL_CORRECTNESS = JudgeMetricSpec(
    name="Technical_Correctness",
    definition=(
        "Technical correctness measures whether the software-engineering "
        "reasoning that connects the evidence to the judgement is valid. The "
        "question is not whether the conclusion feels right but whether it "
        "follows. The recurring invalid inferences in automated code analysis "
        "are well known: treating lines added as a proxy for code quality, "
        "reading the existence of a test file as evidence of test coverage, "
        "reading a CI configuration file as evidence that CI passes, and "
        "treating a ticket marked Done as proof that code was merged and "
        "shipped. An output that explicitly declines to make one of these "
        "leaps, and says why, is demonstrating the behaviour this metric "
        "rewards most."
    ),
    tests=(
        ("Volume of code, lines added or commit count, is not used as a proxy "
        "for code quality."),
        ("The presence of tests is kept distinct from the extent of test "
        "coverage, and coverage is only claimed where a coverage metric exists."),
        ("A CI or workflow configuration file is kept distinct from evidence "
        "that the pipeline actually ran or passed."),
        ("A ticket status is kept distinct from code being merged, reviewed or "
        "deployed."),
        ("Collaboration metrics and peer scores are read as association, not as "
        "proof of cause."),
    ),
    anchors={
        5: "Every inference from evidence to judgement is technically valid, "
           "and the output explicitly declines at least one unsupported leap "
           "where the evidence invites one.",
        4: "Reasoning is sound throughout, with one minor technical imprecision "
           "that does not change the conclusion.",
        3: "One clearly invalid inference, for example treating added lines as "
           "quality or a test file as coverage, which affects one dimension.",
        2: "Multiple invalid inferences. The conclusions do not follow from the "
           "evidence that is cited for them.",
        1: "Technically wrong about what the artifacts are, misreading what a "
           "file, pipeline, status or metric actually represents.",
    },
    grading_context_columns=("artifact_bundle", "gold_reference"),
    examples=(_CORRECTNESS_HIGH, _CORRECTNESS_LOW),
)


EVIDENCE_SPECIFICITY = JudgeMetricSpec(
    name="Evidence_Specificity",
    definition=(
        "Evidence specificity measures whether the assessment anchors its "
        "judgements to hard, checkable identifiers rather than to unverifiable "
        "prose. A hard anchor is a commit SHA, a Jira ticket key, a file path "
        "or a named metric with its value. Quantifiers such as several "
        "commits, mostly complete or generally good are not anchors: a human "
        "marker cannot audit them, and neither can a downstream grounding "
        "check. This metric is scored independently of whether the claims are "
        "true, which is Code Faithfulness, because a specific-but-wrong claim "
        "and a vague-but-safe one are different problems with different fixes."
    ),
    tests=(
        ("Each scored dimension cites at least one hard anchor, a commit SHA, a "
        "ticket key, a file path or a named metric with a value."),
        ("Each anchor is tied to the dimension it is cited for by at least one "
        "sentence of explanation."),
        ("Unverifiable quantifiers are not doing the work that an anchor should "
        "be doing."),
    ),
    anchors={
        5: "Every scored dimension cites at least one hard anchor and ties it "
           "to the judgement in a sentence.",
        4: "All but one scored dimension is anchored, and the unanchored one is "
           "a dimension with genuinely thin evidence in the bundle.",
        3: "About half the dimensions are anchored; the rest rest on prose "
           "alone.",
        2: "Anchors are present in name only, generic references such as "
           "several commits or the test file, with no identifier.",
        1: "No hard anchors anywhere in the output.",
    },
    grading_context_columns=("artifact_bundle",),
    examples=(_SPECIFICITY_HIGH, _SPECIFICITY_LOW),
)


RUBRIC_ADHERENCE = JudgeMetricSpec(
    name="Rubric_Adherence",
    definition=(
        "Rubric adherence measures whether the number awarded is the number "
        "the published rubric band calls for, given the evidence the output "
        "itself presents. The failure mode is score inflation: a narrative "
        "that describes band-three evidence while awarding a nine, or that "
        "justifies a score on grounds the rubric does not list, such as effort, "
        "attitude or improvement over last sprint. This is judged against the "
        "rubric criteria text supplied as grading context, not against the "
        "judge's own taste, and the gold reference is provided as a second "
        "opinion on where the band should fall rather than as the answer key."
    ),
    tests=(
        ("The evidence the output presents falls inside the published band for "
        "the score it awarded."),
        ("The stated reasons for the score are criteria the published rubric "
        "lists for that dimension, not effort, attitude or improvement."),
        ("The direction and size of any disagreement with the gold reference is "
        "explainable from the evidence rather than arbitrary."),
    ),
    anchors={
        5: "The evidence presented places every score inside its published "
           "band, and the reasons given are rubric criteria.",
        4: "Scores sit inside their bands, with one score justified partly on a "
           "non-rubric ground such as effort.",
        3: "At least one score sits one band away from what the output's own "
           "evidence supports.",
        2: "Several scores sit outside the band their evidence supports, "
           "consistently in the same direction.",
        1: "Scores are two or more bands away from the evidence, or are "
           "justified on grounds the rubric does not contain at all.",
    },
    grading_context_columns=("rubric_criteria", "gold_reference"),
    examples=(_ADHERENCE_HIGH, _ADHERENCE_LOW),
)


JUDGE_METRIC_SPECS: tuple[JudgeMetricSpec, ...] = (
    CODE_FAITHFULNESS,
    BUG_ACTIONABILITY,
    TECHNICAL_CORRECTNESS,
    EVIDENCE_SPECIFICITY,
    RUBRIC_ADHERENCE,
)

JUDGE_METRIC_NAMES: tuple[str, ...] = tuple(spec.name for spec in JUDGE_METRIC_SPECS)

SPEC_BY_NAME: dict[str, JudgeMetricSpec] = {spec.name: spec for spec in JUDGE_METRIC_SPECS}


def selected_specs(only: Sequence[str] | None = None) -> tuple[JudgeMetricSpec, ...]:
    if not only:
        return JUDGE_METRIC_SPECS
    missing = set(only) - set(SPEC_BY_NAME)
    if missing:
        raise KeyError(f"Unknown judge metrics: {sorted(missing)}")
    return tuple(SPEC_BY_NAME[name] for name in only)


def build_genai_metrics(
    judge_uri: str,
    *,
    only: Sequence[str] | None = None,
    max_workers: int = 1,
    two_stage: bool = False,
) -> list[Any]:
    """Instantiate the GenAI metrics. ``only`` restricts to named metrics."""
    return [
        spec.build(judge_uri, max_workers=max_workers, two_stage=two_stage)
        for spec in selected_specs(only)
    ]


# =============================================================================
# Part 3 -- Deterministic, LLM-free checks
# =============================================================================
#
# These run before any judge is called, cost nothing, and are exactly
# reproducible. Three reasons they are not optional extras:
#
#  1. They bound the judge. If `citation_anchor_rate` says 40 percent of
#     citations contain no identifier present in the bundle, a Code
#     Faithfulness score of 5 is prima facie wrong and the judge is the thing
#     under suspicion, not the candidate.
#  2. They are the only metrics that survive a judge outage. A run where
#     Ollama died still yields a defensible structural comparison.
#  3. They separate "the model produced nothing usable" from "the model
#     produced something and it was poor". Averaging those together is the
#     single most common way an eval overstates a weak model.

# A hard anchor: a commit SHA, a Jira-style key, or a dotted path/filename.
# Deliberately stricter than services/grounding.py's token pattern, which is
# tuned for recall when deciding whether to DROP a citation. Here we are
# measuring specificity, so a 4-character word must not count as an anchor.
_HARD_ANCHOR = re.compile(
    r"\b(?:[0-9a-f]{7,40}"             # commit SHA (short or full)
    r"|[A-Z][A-Z0-9]{1,9}-\d+"          # JIRA-style ticket key
    r"|[\w./-]+\.[A-Za-z]{1,5})\b"      # filename or dotted path
)

_CODE_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)

# Phrases that mark a recommendation as content-free. Mirrors the spirit of
# llm_client's _GENERIC_COMMIT_MESSAGES: a closed list of things observed in
# real model output, matched case-insensitively as substrings.
_GENERIC_FILLER = (
    "communicate better",
    "improve communication",
    "keep up the good work",
    "keep it up",
    "continue to improve",
    "continue improving",
    "work harder",
    "try harder",
    "be more proactive",
    "maintain momentum",
    "going forward",
    "best practices",
    "more collaboration",
    "stay consistent",
    "overall good job",
)

# Quantifiers that masquerade as evidence.
_VAGUE_QUANTIFIERS = (
    "several commits",
    "many commits",
    "a few commits",
    "mostly complete",
    "generally good",
    "some tickets",
    "various files",
    "a number of",
)

_PYTHON_FENCE_LANGUAGES = {"", "py", "python", "python3"}


# -- 3a. Structural validity --------------------------------------------------

def schema_round_trip_ok(raw: Mapping[str, Any] | None) -> bool:
    """Does the candidate output re-validate as a SprintAssessment?

    The structural analogue of an AST parse for this project: our models emit
    a typed assessment, not source code, so Pydantic validation is the
    grammar check. A model that scores well on content but fails here cannot
    be deployed, and that distinction must survive into the report.
    """
    if raw is None:
        return False
    try:
        SprintAssessment(**dict(raw))
    except Exception:  # noqa: BLE001 - any validation failure is the same answer
        return False
    return True


def python_snippet_syntax_valid(text: str) -> float | None:
    """AST-validity of any Python shown inside the assessment prose.

    Returns the fraction of fenced Python blocks that ``ast.parse`` accepts,
    or ``None`` when the output contains no Python at all. ``None`` rather
    than ``1.0`` is the honest answer for "nothing to check": scoring an
    assessment that showed no code as perfectly syntactic would silently
    reward models that never illustrate a fix, and would put a fake 1.0 into
    every mean.

    This fires on recommendations like "replace the handler with: ```python
    ...```", which are the cases where a syntax error is a real defect a
    student would hit.
    """
    blocks = [
        body
        for language, body in _CODE_FENCE.findall(text or "")
        if language.strip().lower() in _PYTHON_FENCE_LANGUAGES
    ]
    if not blocks:
        return None
    valid = 0
    for body in blocks:
        try:
            # Dedent-tolerant: models often indent a snippet to match prose.
            ast.parse(textwrap.dedent(body))
            valid += 1
        except SyntaxError as error:
            # The measurement itself: an invalid snippet is a finding, so it
            # is logged rather than swallowed, and the row still scores.
            log.debug("Python snippet failed to parse: %s", error)
        except (ValueError, MemoryError, RecursionError) as error:
            # ast.parse raises ValueError on null bytes and can exhaust the
            # recursion limit on pathological nesting. Both mean "not valid
            # Python we can accept", not "the eval crashed".
            log.debug("Python snippet rejected by the parser: %s", error)
    return valid / len(blocks)


# -- 3b. Citation grounding and specificity ----------------------------------

def _bundle_corpus(bundle: ArtifactBundle) -> str:
    return json.dumps(bundle.model_dump(mode="json"), ensure_ascii=True)


def citation_anchor_metrics(
    bundle: ArtifactBundle, assessment: SprintAssessment
) -> dict[str, Any]:
    """Evidence SPECIFICITY: do citations carry hard, checkable identifiers?

    Deliberately does NOT recompute groundedness. ``summarise_example`` in
    ``research.eval.metrics`` already derives ``groundedness_rate`` from
    ``find_ungrounded_citations``, and ``build_eval_frame`` carries that
    column through unchanged -- two implementations of the same quantity is
    how two pipelines end up disagreeing about the same run.

    Specificity is a genuinely different question, and the GAP between the
    two is the diagnostic worth having: a high anchor rate with a low
    groundedness rate is a model inventing plausible-looking commit SHAs,
    which is the worst failure mode for a grading tool and is invisible to
    either metric on its own.
    """
    anchored = 0
    total = 0
    per_dimension_anchored = 0
    scored_dimensions = 0

    for dimension in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dimension, None)
        if score is None or score.evaluation_failed:
            continue
        scored_dimensions += 1
        citations = list(score.evidence_citations or [])
        total += len(citations)
        dimension_has_anchor = False
        for citation in citations:
            if _HARD_ANCHOR.search(citation.identifier or ""):
                anchored += 1
                dimension_has_anchor = True
        if dimension_has_anchor:
            per_dimension_anchored += 1

    return {
        # None, not 1.0, when there is nothing to check -- same reasoning as
        # python_snippet_syntax_valid above.
        "citation_anchor_rate": (anchored / total) if total else None,
        "dimension_anchor_coverage": (
            per_dimension_anchored / scored_dimensions if scored_dimensions else None
        ),
    }


# -- 3c. Assessment "lint" ----------------------------------------------------

def lint_assessment(assessment: SprintAssessment) -> dict[str, Any]:
    """Rule-based warnings over the assessment, in the spirit of a linter.

    Each rule encodes a defect we can define without a model: filler text, a
    justification too short to carry evidence, duplicate citations padding
    the count, a dimension missing entirely, an overall score inconsistent
    with its own rubric scores. The count is a metric; the list is logged as
    an artifact so a failure is explainable rather than merely counted.
    """
    warnings: list[str] = []

    for index, recommendation in enumerate(assessment.key_recommendations or []):
        lowered = recommendation.lower()
        if any(phrase in lowered for phrase in _GENERIC_FILLER):
            warnings.append(f"generic_recommendation: key_recommendations[{index}]")
        if not _HARD_ANCHOR.search(recommendation):
            warnings.append(f"unanchored_recommendation: key_recommendations[{index}]")

    if not assessment.key_recommendations:
        warnings.append("no_recommendations")

    seen_citations: set[str] = set()
    for dimension in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dimension, None)
        if score is None:
            warnings.append(f"missing_dimension: {dimension}")
            continue
        if score.evaluation_failed:
            warnings.append(f"failed_dimension: {dimension}")
            continue
        if len((score.justification or "").split()) < 12:
            warnings.append(f"thin_justification: {dimension}")
        if not score.evidence_citations:
            warnings.append(f"no_citations: {dimension}")
        for citation in score.evidence_citations or []:
            key = (citation.identifier or "").strip().lower()
            if key and key in seen_citations:
                warnings.append(f"duplicate_citation: {dimension} reuses {key[:40]}")
            seen_citations.add(key)
        lowered_justification = (score.justification or "").lower()
        if any(phrase in lowered_justification for phrase in _VAGUE_QUANTIFIERS):
            warnings.append(f"vague_quantifier: {dimension}")

    scored = assessment.rubric_scores.scored()
    if scored:
        rubric_mean = sum(item.score for item in scored) / len(scored)
        # The engine derives overall_score from the rubric scores, so a gap of
        # more than a point means the narrative and the number disagree.
        if abs(assessment.overall_score - rubric_mean) > 1.0:
            warnings.append(
                f"overall_score_inconsistent: overall={assessment.overall_score:.2f} "
                f"rubric_mean={rubric_mean:.2f}"
            )

    return {"lint_warning_count": len(warnings), "lint_warnings": warnings}


# -- 3d. Text-overlap metrics -------------------------------------------------

_WORD = re.compile(r"[A-Za-z0-9_./-]+")


def _tokenise(text: str) -> list[str]:
    return [token.lower() for token in _WORD.findall(text or "")]


def _lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    """Length of the longest common subsequence, O(len(a) * len(b)) time and
    O(len(b)) space. Rolled by hand rather than pulling in ``rouge_score``:
    one new dependency for a 20-line dynamic program is a bad trade in an
    environment a marker has to reproduce, and this is the same quantity
    ROUGE-L is defined on."""
    if not a or not b:
        return 0
    previous = [0] * (len(b) + 1)
    for token_a in a:
        current = [0] * (len(b) + 1)
        for index_b, token_b in enumerate(b, start=1):
            if token_a == token_b:
                current[index_b] = previous[index_b - 1] + 1
            else:
                current[index_b] = max(previous[index_b], current[index_b - 1])
        previous = current
    return previous[-1]


def rouge_l_f1(prediction: str, reference: str, beta: float = 1.2) -> float | None:
    """ROUGE-L F-measure between the candidate and the gold narrative.

    Reported as a *descriptive* statistic only, never as a quality metric.
    Two assessments can describe the same sprint correctly in entirely
    different words, so a low ROUGE-L is not evidence of a bad assessment --
    but a near-1.0 ROUGE-L against gold IS evidence worth investigating,
    because it suggests leakage of the reference into the prompt rather than
    independent analysis. That is what we use it for.

    ``beta`` weights recall over precision, following the original ROUGE-L
    definition, so a candidate that covers the reference is not penalised for
    adding detail.
    """
    tokens_prediction = _tokenise(prediction)
    tokens_reference = _tokenise(reference)
    if not tokens_prediction or not tokens_reference:
        return None
    lcs = _lcs_length(tokens_prediction, tokens_reference)
    if lcs == 0:
        return 0.0
    precision = lcs / len(tokens_prediction)
    recall = lcs / len(tokens_reference)
    beta_squared = beta * beta
    return ((1 + beta_squared) * precision * recall) / (recall + beta_squared * precision)


def token_overlap_f1(prediction: str, reference: str) -> float | None:
    """Bag-of-words F1. Complements ROUGE-L by ignoring order, which makes it
    insensitive to the dimension ordering the perturbation probe shuffles."""
    tokens_prediction = _tokenise(prediction)
    tokens_reference = _tokenise(reference)
    if not tokens_prediction or not tokens_reference:
        return None
    set_prediction, set_reference = set(tokens_prediction), set(tokens_reference)
    overlap = len(set_prediction & set_reference)
    if overlap == 0:
        return 0.0
    precision = overlap / len(set_prediction)
    recall = overlap / len(set_reference)
    return 2 * precision * recall / (precision + recall)


# NOTE on BERTScore: deliberately not implemented. It needs a transformer
# download and a GPU slice that would compete with the judge for VRAM, and
# for citation checking an exact-anchor metric (citation_anchor_rate above)
# is strictly more informative than embedding similarity -- a fabricated SHA
# is embedding-similar to a real one, which is exactly the case we must
# catch. `semantic_similarity_hook` is the extension point if a reviewer
# insists.
SEMANTIC_SIMILARITY_HOOK: Callable[[str, str], float] | None = None


# -- 3e. Arithmetic accuracy against gold -------------------------------------

def numeric_grade_errors(
    candidate: SprintAssessment | None, gold: SprintAssessment
) -> dict[str, float | None]:
    """Per-dimension and overall absolute error against the gold assessment.

    Delegates to ``judges.code_based_scorer.numeric_grade_accuracy``, the
    scorer the trace-based pipeline in ``judges/run_judges.py`` already uses,
    rather than recomputing the same subtraction with its own conventions.
    That keeps ONE definition of grade error in the codebase: if the team
    changes how a failed dimension is treated, both pipelines change
    together, and a number reported here is the same number the MLflow UI
    shows for a trace-based run.

    Feedback names are preserved verbatim (``grade_abs_error_<dim>``,
    ``grade_abs_error_overall``, ``grade_mae_per_dimension``) so the two
    pipelines are comparable without a translation table.

    Two things this adds on top of the existing scorer:
      * it tolerates a missing candidate (a run where the model crashed),
        which the scorer's ``expectations["gold"]`` access path does not;
      * ``grade_signed_error_overall``, because MAE hides direction. A model
        that is +2 on every dimension and one that alternates +2 and -2 have
        identical MAE and completely different problems -- and only the first
        is a correctable calibration issue.
    """
    out: dict[str, float | None] = {}

    if candidate is None:
        for dimension in DIMENSIONS:
            out[f"grade_abs_error_{dimension}"] = None
        out["grade_mae_per_dimension"] = None
        out["grade_abs_error_overall"] = None
        out["grade_signed_error_overall"] = None
        return out

    # Same outputs shape judges/run_judges.py builds for this scorer: a
    # dimension the model never produced is present as None, which is what
    # lets the scorer distinguish "wrong score" from "no score".
    rubric_scores: dict[str, dict | None] = {}
    for dimension in DIMENSIONS:
        score = getattr(candidate.rubric_scores, dimension, None)
        rubric_scores[dimension] = (
            score.model_dump() if score is not None and not score.evaluation_failed else None
        )
    outputs = {
        "rubric_scores": rubric_scores,
        "overall_score": float(candidate.overall_score),
    }
    feedbacks = numeric_grade_accuracy.run(
        outputs=outputs, expectations={"gold": gold.model_dump(mode="json")}
    )
    for feedback in feedbacks:
        out[feedback.name] = (
            float(feedback.value) if feedback.value is not None else None
        )
    # The scorer only emits a feedback for dimensions the candidate scored;
    # fill the rest so every row has the same columns and pandas does not
    # silently widen the frame when one model drops a dimension.
    for dimension in DIMENSIONS:
        out.setdefault(f"grade_abs_error_{dimension}", None)
    out.setdefault("grade_mae_per_dimension", None)
    out.setdefault("grade_abs_error_overall", None)

    out["grade_signed_error_overall"] = float(candidate.overall_score) - float(
        gold.overall_score
    )
    return out


def rank_inversion_rate(frame: pd.DataFrame, score_column: str = "overall_score") -> float | None:
    """Fraction of example pairs a model orders differently from gold.

    The discriminative question: a model whose absolute scores are all two
    points high but which still ranks the five fixtures correctly is far more
    useful to a course than one with perfect MAE and random ordering. MAE
    cannot see that difference; this can.
    """
    needed = {score_column, "gold_overall_score"}
    if not needed.issubset(frame.columns):
        return None
    usable = frame[[score_column, "gold_overall_score"]].apply(
        pd.to_numeric, errors="coerce"
    ).dropna()
    if len(usable) < 2:
        return None
    candidate_values = usable[score_column].to_numpy()
    gold_values = usable["gold_overall_score"].to_numpy()
    total = 0
    inverted = 0
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            gold_delta = gold_values[i] - gold_values[j]
            if gold_delta == 0:
                continue  # gold is indifferent; no ordering to violate
            total += 1
            if np.sign(candidate_values[i] - candidate_values[j]) != np.sign(gold_delta):
                inverted += 1
    return (inverted / total) if total else None


# =============================================================================
# Part 4 -- The hybrid eval frame and mlflow.evaluate() orchestration
# =============================================================================
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


def render_gold_for_judge(gold: SprintAssessment) -> str:
    """Compact gold reference: scores and bottleneck ordering only.

    Deliberately NOT the full gold narrative. Showing the judge a complete
    human-written assessment invites it to score candidates on textual
    similarity to gold rather than on the rubric, which would make
    Bug_Actionability a paraphrase detector.
    """
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
    gold: SprintAssessment
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

    Layered deliberately on top of ``research.eval.metrics.summarise_example``
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
      grade_*            delegated to judges.code_based_scorer
      human_<metric>     optional human annotations for Part 5
    """
    if not records:
        raise ValueError("build_eval_frame received no records.")

    rubric_criteria = render_rubric_criteria()
    rows: list[dict[str, Any]] = []

    for record in records:
        candidate = record.candidate
        prediction = render_assessment_for_judge(candidate, record.error)
        target = render_assessment_for_judge(record.gold)

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
            "rouge_l_vs_gold": rouge_l_f1(prediction, target),
            "token_overlap_vs_gold": token_overlap_f1(prediction, target),
            "latency_s": record.latency_s,
            "gold_overall_score": float(record.gold.overall_score),
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
    # --- inherited verbatim from research.eval.metrics.summarise_example ---
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
    # --- delegated to judges.code_based_scorer.numeric_grade_accuracy ---
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


# -- 4d. Provenance ----------------------------------------------------------

def _git_sha() -> str:
    import subprocess

    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:  # noqa: BLE001 - absent git is not an eval failure
        return "unknown"


def _judge_model_digest(judge_model: str) -> str:
    """Ollama manifest digest for the judge weights.

    A model TAG is not provenance: the same tag can be re-pulled at a
    different quantisation, which changes judge behaviour while leaving every
    run name identical. The digest pins what actually graded.
    """
    try:
        import httpx

        base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").replace("/v1", "")
        response = httpx.post(f"{base}/api/show", json={"name": judge_model}, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
        digest = payload.get("digest") or payload.get("model_info", {}).get("general.digest")
        return (digest or "unknown")[:16]
    except Exception:  # noqa: BLE001
        return "unknown"


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
    # the same path services/ and judges/ use, rather than a second
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
            "judge_model_digest": _judge_model_digest(judge_model),
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
            "git_sha": _git_sha(),
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
            targets="target",
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


# =============================================================================
# Part 5 -- Meta-evaluation: is the judge measuring anything?
# =============================================================================
#
# This is the part that makes the rest of the numbers reportable. An LLM
# judge is a measurement instrument, and an instrument with no stated
# reliability produces results a reader is entitled to ignore. We report a
# panel of coefficients rather than one, because each is blind to a different
# failure:
#
#   Cohen's kappa          chance-corrected exact agreement. Catches a judge
#                          that looks accurate only because the human
#                          distribution is skewed.
#   Quadratic-weighted kappa  the headline for an ORDERED 1-5 rubric: a 5-vs-4
#                          disagreement should not be penalised like 5-vs-1.
#                          This is the standard for ordinal rater agreement.
#   Spearman rho           rank agreement. A judge that is uniformly two
#                          points harsh is still perfectly useful for RANKING
#                          models, and only rho shows that.
#   Kendall tau-b          rho's robustness check; handles the heavy ties a
#                          5-point scale produces better than rho does.
#   Pearson r              linear agreement, reported only to be compared
#                          against rho. r much greater than rho means a
#                          single outlier row is carrying the correlation.
#   Krippendorff's alpha   handles missing annotations natively, which matters
#                          because human annotation coverage is partial.
#   ICC(2,1)               absolute agreement, not just covariation. Two
#                          raters can correlate at 0.95 and still be three
#                          points apart on every item.
#   Mean signed error      the bias term. Positive means the judge is more
#                          generous than the human, which is the documented
#                          failure mode of LLM judges and the one most likely
#                          to flatter our own system.
#
# Everything is reported with a bootstrap CI and an n. A kappa from eight
# annotated rows is an anecdote, and the report says so rather than leaving
# the reader to guess.

# Landis & Koch (1977) bands. Conventional, widely understood by markers and
# reviewers, and stated explicitly so nobody has to guess what "good" means.
_KAPPA_BANDS = (
    (0.81, "almost perfect"),
    (0.61, "substantial"),
    (0.41, "moderate"),
    (0.21, "fair"),
    (0.01, "slight"),
    (-1.01, "poor / no better than chance"),
)


def interpret_kappa(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "not estimable"
    for threshold, label in _KAPPA_BANDS:
        if value >= threshold:
            return label
    return "poor / no better than chance"


def bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[np.ndarray], float] = np.mean,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float | None, float | None, float | None]:
    """Percentile bootstrap CI for an arbitrary statistic.

    Percentile rather than BCa: with the 5-50 row datasets this study
    operates on, the bias-correction and acceleration terms are themselves
    estimated from too little data to be trustworthy, and a plain percentile
    interval is the conservative, explainable choice. Returns (None, None,
    None) below three observations -- an interval from two points is theatre.
    """
    array = np.asarray([v for v in values if v is not None and not _is_nan(v)], dtype=float)
    if array.size < 3:
        return (float(statistic(array)) if array.size else None, None, None)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(n_boot, array.size))
    draws = np.array([statistic(array[row]) for row in indices], dtype=float)
    draws = draws[~np.isnan(draws)]
    if draws.size == 0:
        return (float(statistic(array)), None, None)
    low, high = np.quantile(draws, [alpha / 2, 1 - alpha / 2])
    return float(statistic(array)), float(low), float(high)


def _is_nan(value: Any) -> bool:
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def _paired_bootstrap_statistic(
    x: np.ndarray,
    y: np.ndarray,
    statistic: Callable[[np.ndarray, np.ndarray], float],
    *,
    n_boot: int = 2000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float | None, float | None]:
    """CI for a two-sample paired statistic (kappa, rho) by resampling PAIRS.

    Resampling pairs, not each vector independently, is what keeps the
    pairing intact -- bootstrapping the two rater vectors separately would
    destroy exactly the association being measured.
    """
    if x.size < 3:
        return (None, None)
    rng = np.random.default_rng(seed)
    draws: list[float] = []
    degenerate = 0
    for _ in range(n_boot):
        index = rng.integers(0, x.size, size=x.size)
        try:
            value = statistic(x[index], y[index])
        except (ValueError, ZeroDivisionError, FloatingPointError):
            # A resample can land on a single rating level, where kappa and
            # rho are undefined. Skipping those draws is correct; counting
            # them is what tells us whether the interval is trustworthy.
            degenerate += 1
            continue
        if value is not None and not _is_nan(value):
            draws.append(float(value))
    if degenerate:
        log.debug(
            "%d of %d bootstrap resamples were degenerate (single rating level).",
            degenerate, n_boot,
        )
    if len(draws) < 20:
        # Too few usable draws for a percentile interval to mean anything --
        # which is itself a signal that the ratings have almost no variance.
        log.warning(
            "Bootstrap CI not estimable: only %d of %d resamples yielded a "
            "defined statistic.", len(draws), n_boot,
        )
        return (None, None)
    low, high = np.quantile(np.asarray(draws), [alpha / 2, 1 - alpha / 2])
    return (float(low), float(high))


def krippendorff_alpha_ordinal(ratings: np.ndarray) -> float | None:
    """Krippendorff's alpha with the ordinal difference function.

    ``ratings`` is (n_raters, n_items); NaN marks a missing judgement. Hand
    implemented because the ``krippendorff`` package is not in this project's
    requirements and a reproducibility claim gets weaker with every optional
    dependency a reader has to install. Alpha earns its place over kappa
    because it handles unequal annotation coverage natively -- our human
    annotations are partial by construction.
    """
    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return None

    # Units with at least two ratings are the only ones alpha is defined over.
    usable = matrix[:, np.sum(~np.isnan(matrix), axis=0) >= 2]
    if usable.shape[1] < 2:
        return None

    values = usable[~np.isnan(usable)]
    levels = np.unique(values)
    if levels.size < 2:
        return None  # no variance: alpha is undefined, not 1.0

    # Ordinal difference: squared distance in cumulative rank mass.
    counts = {level: float(np.sum(values == level)) for level in levels}
    cumulative: dict[float, float] = {}
    running = 0.0
    for level in levels:
        cumulative[level] = running + counts[level] / 2.0
        running += counts[level]

    def ordinal_delta(a: float, b: float) -> float:
        return (cumulative[a] - cumulative[b]) ** 2

    observed_numerator = 0.0
    observed_pairs = 0.0
    for column in usable.T:
        present = column[~np.isnan(column)]
        m = present.size
        if m < 2:
            continue
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                observed_numerator += ordinal_delta(present[i], present[j]) / (m - 1)
                observed_pairs += 1.0 / (m - 1)
    if observed_pairs == 0:
        return None
    observed_disagreement = observed_numerator / observed_pairs

    total = values.size
    expected_numerator = 0.0
    for a in levels:
        for b in levels:
            if a == b:
                continue
            expected_numerator += counts[a] * counts[b] * ordinal_delta(a, b)
    expected_disagreement = expected_numerator / (total * (total - 1))
    if expected_disagreement == 0:
        return None
    return float(1.0 - observed_disagreement / expected_disagreement)


def icc_2_1(ratings: np.ndarray) -> float | None:
    """ICC(2,1): two-way random effects, absolute agreement, single rater.

    Reported alongside the correlations because they answer different
    questions. A judge that scores every output exactly two points above the
    human correlates at r = 1.0 and has an ICC near zero -- and for a grading
    tool whose scores students see, absolute agreement is the one that
    matters. Needs complete rows, so it runs on the listwise-complete subset
    and reports its own n via the caller.
    """
    matrix = np.asarray(ratings, dtype=float)
    if matrix.ndim != 2:
        return None
    matrix = matrix[:, ~np.isnan(matrix).any(axis=0)]  # listwise-complete items
    n_raters, n_items = matrix.shape
    if n_items < 3 or n_raters < 2:
        return None

    grand_mean = matrix.mean()
    item_means = matrix.mean(axis=0)
    rater_means = matrix.mean(axis=1)

    ss_items = n_raters * np.sum((item_means - grand_mean) ** 2)
    ss_raters = n_items * np.sum((rater_means - grand_mean) ** 2)
    ss_total = np.sum((matrix - grand_mean) ** 2)
    ss_error = ss_total - ss_items - ss_raters

    df_items = n_items - 1
    df_raters = n_raters - 1
    df_error = df_items * df_raters
    if df_error <= 0:
        return None

    ms_items = ss_items / df_items
    ms_raters = ss_raters / df_raters
    ms_error = ss_error / df_error

    denominator = ms_items + df_raters * ms_error + (n_raters * (ms_raters - ms_error)) / n_items
    if denominator == 0:
        return None
    return float((ms_items - ms_error) / denominator)


@dataclass
class CalibrationReport:
    """Everything needed to decide how far to trust one judge metric."""

    metric: str
    n: int
    n_available: int
    exact_agreement: float | None = None
    within_one_agreement: float | None = None
    cohen_kappa: float | None = None
    cohen_kappa_ci: tuple[float | None, float | None] = (None, None)
    quadratic_kappa: float | None = None
    quadratic_kappa_ci: tuple[float | None, float | None] = (None, None)
    spearman_rho: float | None = None
    spearman_p: float | None = None
    spearman_ci: tuple[float | None, float | None] = (None, None)
    kendall_tau: float | None = None
    kendall_p: float | None = None
    pearson_r: float | None = None
    krippendorff_alpha: float | None = None
    icc_2_1: float | None = None
    mae: float | None = None
    mean_signed_error: float | None = None
    judge_mean: float | None = None
    human_mean: float | None = None
    judge_distinct_scores: int = 0
    interpretation: str = "not estimable"
    warnings: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        row = {
            key: value
            for key, value in self.__dict__.items()
            if not isinstance(value, (tuple, list))
        }
        row["cohen_kappa_ci_low"], row["cohen_kappa_ci_high"] = self.cohen_kappa_ci
        row["quadratic_kappa_ci_low"], row["quadratic_kappa_ci_high"] = self.quadratic_kappa_ci
        row["spearman_ci_low"], row["spearman_ci_high"] = self.spearman_ci
        row["warnings"] = "; ".join(self.warnings)
        return row


def evaluate_judge_calibration(
    frame: pd.DataFrame,
    metric: str,
    *,
    judge_column: str | None = None,
    human_column: str | None = None,
    n_boot: int = 2000,
    seed: int = 42,
) -> CalibrationReport:
    """Agreement between the LLM judge and the human baseline for one metric.

    Operates on whichever rows have BOTH a judge score and a human
    annotation, and reports that count as ``n`` next to the total available.
    Every coefficient is None rather than a plausible-looking number when the
    data cannot support it -- a kappa of 0.0 and an unestimable kappa mean
    very different things to a reader.
    """
    from scipy import stats as scipy_stats  # type: ignore[import-untyped]
    from sklearn.metrics import cohen_kappa_score  # type: ignore[import-untyped]

    judge_col = judge_column or f"judge_{metric}"
    human_col = human_column or f"human_{metric}"

    missing = [column for column in (judge_col, human_col) if column not in frame.columns]
    if missing:
        return CalibrationReport(
            metric=metric,
            n=0,
            n_available=len(frame),
            warnings=[f"missing columns: {', '.join(missing)}"],
        )

    paired = frame[[judge_col, human_col]].apply(pd.to_numeric, errors="coerce").dropna()
    n = len(paired)
    report = CalibrationReport(metric=metric, n=n, n_available=len(frame))

    if n == 0:
        report.warnings.append("no rows carry both a judge score and a human annotation")
        return report

    judge_values = paired[judge_col].to_numpy(dtype=float)
    human_values = paired[human_col].to_numpy(dtype=float)

    report.judge_mean = float(judge_values.mean())
    report.human_mean = float(human_values.mean())
    report.mae = float(np.mean(np.abs(judge_values - human_values)))
    # Signed, judge minus human: positive is a lenient judge.
    report.mean_signed_error = float(np.mean(judge_values - human_values))

    judge_int = np.rint(judge_values).astype(int)
    human_int = np.rint(human_values).astype(int)
    report.exact_agreement = float(np.mean(judge_int == human_int))
    report.within_one_agreement = float(np.mean(np.abs(judge_int - human_int) <= 1))
    report.judge_distinct_scores = int(np.unique(judge_int).size)

    if report.judge_distinct_scores == 1:
        # The single most common silent failure: a judge that answers 4 to
        # everything scores a respectable MAE and a kappa of exactly 0.
        report.warnings.append(
            f"judge returned the constant value {judge_int[0]} on every row -- "
            "it is not discriminating, and no correlation is interpretable"
        )

    if n < 10:
        report.warnings.append(
            f"n={n} is too small for a stable agreement coefficient; treat "
            "every figure here as indicative only"
        )

    labels = sorted(set(judge_int.tolist()) | set(human_int.tolist()))
    if len(labels) >= 2:
        try:
            report.cohen_kappa = float(
                cohen_kappa_score(human_int, judge_int, labels=labels)
            )
            report.quadratic_kappa = float(
                cohen_kappa_score(human_int, judge_int, labels=labels, weights="quadratic")
            )
            report.cohen_kappa_ci = _paired_bootstrap_statistic(
                human_int.astype(float),
                judge_int.astype(float),
                lambda a, b: cohen_kappa_score(
                    np.rint(a).astype(int), np.rint(b).astype(int)
                ),
                n_boot=n_boot,
                seed=seed,
            )
            report.quadratic_kappa_ci = _paired_bootstrap_statistic(
                human_int.astype(float),
                judge_int.astype(float),
                lambda a, b: cohen_kappa_score(
                    np.rint(a).astype(int), np.rint(b).astype(int), weights="quadratic"
                ),
                n_boot=n_boot,
                seed=seed,
            )
        except Exception:  # noqa: BLE001
            report.warnings.append("kappa could not be computed on this label set")
    else:
        report.warnings.append("only one rating level present; kappa undefined")

    if n >= 3 and np.std(judge_values) > 0 and np.std(human_values) > 0:
        rho = scipy_stats.spearmanr(judge_values, human_values)
        report.spearman_rho = float(rho.statistic)
        report.spearman_p = float(rho.pvalue)
        report.spearman_ci = _paired_bootstrap_statistic(
            judge_values,
            human_values,
            lambda a, b: float(scipy_stats.spearmanr(a, b).statistic),
            n_boot=n_boot,
            seed=seed,
        )
        tau = scipy_stats.kendalltau(judge_values, human_values, variant="b")
        report.kendall_tau = float(tau.statistic)
        report.kendall_p = float(tau.pvalue)
        report.pearson_r = float(scipy_stats.pearsonr(judge_values, human_values).statistic)
    else:
        report.warnings.append(
            "no variance in at least one rater; rank correlation undefined"
        )

    stacked = np.vstack([human_values, judge_values])
    report.krippendorff_alpha = krippendorff_alpha_ordinal(stacked)
    report.icc_2_1 = icc_2_1(stacked)

    # Headline interpretation follows quadratic kappa: the rubric is ordinal,
    # so near-miss disagreements should not be treated as total disagreements.
    report.interpretation = interpret_kappa(
        report.quadratic_kappa if report.quadratic_kappa is not None else report.cohen_kappa
    )
    return report


def calibration_table(
    frame: pd.DataFrame,
    metrics: Sequence[str] = JUDGE_METRIC_NAMES,
    **kwargs: Any,
) -> pd.DataFrame:
    """One calibration row per judge metric, ready to log or print."""
    rows = [
        evaluate_judge_calibration(frame, metric, **kwargs).to_row() for metric in metrics
    ]
    return pd.DataFrame(rows).set_index("metric")


# =============================================================================
# Part 6 -- Bias mitigation: pairwise comparison with position-swap debiasing
# =============================================================================
#
# Absolute 1-5 scoring has a known weakness: local judges compress onto the
# middle of the scale, so two models that differ materially can both land on
# 3. Pairwise comparison recovers that resolution -- but introduces position
# bias, the well-documented tendency of an LLM judge to prefer whichever
# candidate it was shown first, regardless of content.
#
# Every comparison here is therefore run TWICE with the order swapped, and a
# verdict only counts if it survives the swap. Disagreement between the two
# orders is not discarded quietly: it is counted and reported as
# `position_bias_rate`, which is a direct, honest measure of how much of the
# judge's preference is an artifact of presentation. A pairwise study that
# does not report this number is not evidence of anything.


def _judge_call(
    prompt: str,
    judge_uri: str,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Single raw judge completion.

    Routed through the same ``score_model_on_payload`` that
    ``make_genai_metric`` uses internally, rather than a separate OpenAI
    client, so Parts 6 and 7 cannot diverge from the transport the headline
    metrics were produced with -- and so the stub judge in Part 10 covers all
    three paths with one patch.
    """
    from mlflow.metrics.genai import model_utils

    return model_utils.score_model_on_payload(
        judge_uri,
        prompt,
        dict(parameters or judge_parameters()),
        None,
        None,
        "llm/v1/chat",
    )


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


# =============================================================================
# Part 7 -- Robustness: self-consistency and perturbation probes
# =============================================================================
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


# =============================================================================
# Part 8 -- Statistical inference for model comparisons
# =============================================================================
#
# With five fixtures and three models, the difference between "model A is
# better" and "model A scored higher on this sample" is the whole report. Three
# commitments:
#
#   Paired, always. Every model sees the identical examples, so the paired
#     difference removes example difficulty from the comparison -- by far the
#     largest variance component when n is 5.
#   An effect size next to every p. Cliff's delta is reported because it is
#     non-parametric, bounded, and interpretable on an ordinal 1-5 scale,
#     where Cohen's d would assume an interval scale the rubric does not have.
#   Multiplicity correction. Comparing 3 models on 5 metrics is 15 tests; at
#     alpha 0.05 roughly one spurious "significant" result is expected. Holm
#     controls the family-wise error rate for the small confirmatory set;
#     Benjamini-Hochberg controls FDR for the wider exploratory sweep. Both
#     are provided and the choice is recorded in the output.


def holm_bonferroni(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values. Controls FWER; use for the headline
    confirmatory comparisons, where one false claim is costly."""
    values = [(p, index) for index, p in enumerate(pvalues) if p is not None and not _is_nan(p)]
    adjusted: list[float | None] = [None] * len(pvalues)
    running = 0.0
    m = len(values)
    for rank, (p, index) in enumerate(sorted(values)):
        running = max(running, (m - rank) * p)
        adjusted[index] = min(1.0, running)
    return [1.0 if value is None else value for value in adjusted]


def benjamini_hochberg(pvalues: Sequence[float]) -> list[float]:
    """BH step-up adjusted p-values. Controls FDR; use for the exploratory
    sweep across many metrics, where tolerating some false positives in
    exchange for power is the right trade."""
    values = [(p, index) for index, p in enumerate(pvalues) if p is not None and not _is_nan(p)]
    adjusted: list[float | None] = [None] * len(pvalues)
    m = len(values)
    running = 1.0
    for rank, (p, index) in enumerate(sorted(values, reverse=True)):
        position = m - rank
        running = min(running, p * m / position)
        adjusted[index] = min(1.0, running)
    return [1.0 if value is None else value for value in adjusted]


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> tuple[float | None, str]:
    """Cliff's delta plus its conventional magnitude label.

    delta is P(a > b) - P(a < b): the probability that a randomly chosen
    observation from A beats one from B, rescaled to [-1, 1]. No normality or
    interval-scale assumption, which is what makes it the right effect size
    for a 1-5 rubric. Thresholds follow Romano et al. (2006).
    """
    x = np.asarray([v for v in a if v is not None and not _is_nan(v)], dtype=float)
    y = np.asarray([v for v in b if v is not None and not _is_nan(v)], dtype=float)
    if x.size == 0 or y.size == 0:
        return None, "not estimable"
    greater = int(np.sum(x[:, None] > y[None, :]))
    less = int(np.sum(x[:, None] < y[None, :]))
    delta = (greater - less) / (x.size * y.size)
    magnitude = abs(delta)
    if magnitude < 0.147:
        label = "negligible"
    elif magnitude < 0.33:
        label = "small"
    elif magnitude < 0.474:
        label = "medium"
    else:
        label = "large"
    return float(delta), label


def paired_model_comparison(
    frame: pd.DataFrame,
    metric: str,
    model_a: str,
    model_b: str,
    *,
    n_boot: int = 10_000,
    seed: int = 42,
    higher_is_better: bool = True,
) -> dict[str, Any]:
    """Paired comparison of two models on one metric.

    Repeats are averaged per (model, example) before pairing: the comparison
    is between models on the same example, so within-model repeat variation
    belongs to the consistency analysis in Part 7, not here.
    """
    from scipy import stats as scipy_stats  # type: ignore[import-untyped]

    if metric not in frame.columns:
        return {"metric": metric, "pair": f"{model_a} vs {model_b}", "n": 0,
                "note": "metric column absent"}

    local = frame.assign(_value=pd.to_numeric(frame[metric], errors="coerce"))
    collapsed = (
        local.groupby(["example_id", "model"])["_value"].mean().reset_index()
    )
    pivot = collapsed.pivot(index="example_id", columns="model", values="_value")
    if model_a not in pivot.columns or model_b not in pivot.columns:
        return {"metric": metric, "pair": f"{model_a} vs {model_b}", "n": 0,
                "note": "one model absent from this metric"}

    pair = pivot[[model_a, model_b]].dropna()
    result: dict[str, Any] = {
        "metric": metric,
        "pair": f"{model_a} vs {model_b}",
        "model_a": model_a,
        "model_b": model_b,
        "higher_is_better": higher_is_better,
        "n": len(pair),
    }

    # The mean difference, its percentile bootstrap CI and the win rate come
    # from research.eval.analysis.paired_bootstrap_diff -- the function the
    # model-comparison report already uses -- so a CI quoted here and a CI
    # quoted by `cli.py analyze` are the same estimator with the same seed,
    # not two bootstraps that happen to be near each other. What this adds on
    # top is a significance test, an effect size, and the power floor, none of
    # which analysis.py computes.
    delegated = paired_bootstrap_diff(
        frame.assign(**{metric: local["_value"]}),
        metric,
        model_a,
        model_b,
        n_boot=n_boot,
        seed=seed,
    )
    # The smallest p-value the Wilcoxon signed-rank test can return at this n,
    # which is 2 / 2**n for a two-sided test. At n=5 that is 0.0625, so NOTHING
    # can reach alpha=0.05 however large the effect -- and after multiplicity
    # correction the floor rises further. Reporting it alongside the p-value is
    # what stops "not significant" being misread as "no difference"; at these
    # sample sizes the CI and the effect size are the evidence, not the p.
    result["min_attainable_p"] = (
        float(2 ** (1 - len(pair))) if len(pair) >= 1 else None
    )
    result["p_can_reach_0.05"] = bool(result["min_attainable_p"] <= 0.05) if pair.size else False

    if len(pair) < 3:
        result["note"] = "fewer than 3 paired examples; no inference attempted"
        return result

    differences = (pair[model_a] - pair[model_b]).to_numpy(dtype=float)
    if delegated is not None:
        result.update({
            "mean_diff": delegated.mean_diff,
            "ci_low": delegated.ci_low,
            "ci_high": delegated.ci_high,
            "median_diff": delegated.median_diff,
            # Ties split, so win_rate is comparable with the pairwise tournament.
            "win_rate_a": delegated.win_rate_a,
        })
    else:
        point, low, high = bootstrap_ci(differences.tolist(), n_boot=n_boot, seed=seed)
        result.update({
            "mean_diff": point,
            "ci_low": low,
            "ci_high": high,
            "median_diff": float(np.median(differences)),
            "win_rate_a": float(
                (differences > 0).mean() + 0.5 * (differences == 0).mean()
            ),
        })

    if np.allclose(differences, 0):
        result["wilcoxon_p"] = 1.0
        result["note"] = "models identical on every paired example"
    else:
        try:
            # Wilcoxon signed-rank, not a paired t-test: n is small and the
            # rubric is ordinal, so normality cannot be assumed.
            test = scipy_stats.wilcoxon(differences, zero_method="zsplit")
            result["wilcoxon_p"] = float(test.pvalue)
        except ValueError as error:
            result["wilcoxon_p"] = None
            result["note"] = f"wilcoxon not applicable: {error}"

    delta, magnitude = cliffs_delta(pair[model_a].tolist(), pair[model_b].tolist())
    result["cliffs_delta"] = delta
    result["effect_magnitude"] = magnitude
    # Read back off the result, not off locals: the CI may have come from the
    # delegated paired_bootstrap_diff rather than from bootstrap_ci here.
    ci_low, ci_high = result.get("ci_low"), result.get("ci_high")
    result["ci_excludes_zero"] = bool(
        ci_low is not None and ci_high is not None and ci_low * ci_high > 0
    )
    return result


def model_comparison_report(
    frame: pd.DataFrame,
    metrics: Sequence[str] | None = None,
    *,
    correction: Literal["holm", "bh", "none"] = "holm",
    **kwargs: Any,
) -> pd.DataFrame:
    """Every model pair against every metric, with multiplicity correction.

    The ``significant`` column uses the CORRECTED p-value and is the only
    column anyone should quote. The raw p is kept beside it so the correction
    is auditable rather than invisible.
    """
    if "model" not in frame.columns:
        raise KeyError("frame has no 'model' column")
    models = sorted(frame["model"].dropna().unique())
    if metrics is None:
        metrics = [
            f"judge_{name}" for name in JUDGE_METRIC_NAMES if f"judge_{name}" in frame.columns
        ] + ["judge_composite"] + [
            column for column, _ in DETERMINISTIC_METRIC_COLUMNS if column in frame.columns
        ]
    direction = {column: better for column, better in DETERMINISTIC_METRIC_COLUMNS}

    rows: list[dict[str, Any]] = []
    for metric in metrics:
        if metric not in frame.columns:
            continue
        for index, model_a in enumerate(models):
            for model_b in models[index + 1:]:
                rows.append(
                    paired_model_comparison(
                        frame,
                        metric,
                        model_a,
                        model_b,
                        higher_is_better=direction.get(metric, True),
                        **kwargs,
                    )
                )
    report = pd.DataFrame(rows)
    if report.empty or "wilcoxon_p" not in report.columns:
        return report

    raw = report["wilcoxon_p"].tolist()
    if correction == "holm":
        report["p_adjusted"] = holm_bonferroni(raw)
    elif correction == "bh":
        report["p_adjusted"] = benjamini_hochberg(raw)
    else:
        report["p_adjusted"] = raw
    report["correction"] = correction
    report["n_tests"] = int(report["wilcoxon_p"].notna().sum())
    report["significant"] = report["p_adjusted"] < 0.05
    if "min_attainable_p" in report.columns:
        underpowered = report[report["min_attainable_p"] > 0.05]
        if not underpowered.empty:
            log.warning(
                "%d of %d comparisons are UNDERPOWERED BY CONSTRUCTION: at n=%s the "
                "Wilcoxon test cannot return p<=0.05 at any effect size. Report the "
                "bootstrap CI and Cliff's delta for these, never the p-value.",
                len(underpowered),
                len(report),
                sorted(underpowered["n"].unique().tolist()),
            )
    return report


# =============================================================================
# Part 9 -- Artifacts: figures, taxonomy, and a judge card
# =============================================================================
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

        # groundedness_rate comes from research.eval.metrics, not from a
        # second implementation here -- see citation_anchor_metrics.
        grounded = row.get("groundedness_rate")
        if grounded is not None and not _is_nan(grounded) and grounded < 1.0:
            tags.append("fabricated_citation")

        anchor = row.get("citation_anchor_rate")
        if anchor is not None and not _is_nan(anchor) and anchor < 0.5:
            tags.append("unanchored_evidence")

        scored = row.get("dimensions_present")
        if scored is not None and not _is_nan(scored) and 0 < scored < len(DIMENSIONS):
            tags.append("incomplete_coverage")

        warnings = row.get("lint_warnings")
        if isinstance(warnings, str) and "generic_recommendation" in warnings:
            tags.append("generic_recommendation")

        signed = row.get("grade_signed_error_overall")
        if signed is not None and not _is_nan(signed):
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
            and not _is_nan(correctness)
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
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M UTC} | git {_git_sha()}",
        "",
        "## 1. What this judge is",
        "",
        f"- Judge model: `{judge_model}` (digest `{_judge_model_digest(judge_model)}`)",
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
                return "n/a" if value is None or _is_nan(value) else f"{float(value):.{digits}f}"

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
                f"{'n/a' if alpha is None or _is_nan(alpha) else format(float(alpha), '.2f')}"
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
                    if value is not None and not _is_nan(value):
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


# =============================================================================
# Part 10 -- Record loading, a stub judge, and the CLI
# =============================================================================

def gold_by_fixture() -> dict[str, SprintAssessment]:
    """Map each benchmark fixture key to its human-authored gold assessment."""
    from schemas import benchmark

    return {
        "high_performing": benchmark.high_performing_grade,
        "struggling": benchmark.struggling_grade,
        "good_collab_low_output": benchmark.good_collab_low_output_grade,
        "imbalanced_high_output": benchmark.imbalanced_high_output_grade,
        "lone_contributor_poor_outcome": benchmark.lone_contributor_poor_outcome_grade,
    }


def load_records_from_run(
    run_id: str,
    *,
    model: str | None = None,
    human_annotations: str | Path | None = None,
) -> list[JudgeRecord]:
    """Rebuild JudgeRecords from a `research.eval.runner` MLflow run.

    The runner already logs each candidate SprintAssessment to
    `raw_outputs/raw__<example>__r<n>.json`, so judging reads from MLflow
    rather than re-running the candidate models. That matters for more than
    cost: it guarantees the judged artifact is byte-identical to the one the
    deterministic metrics in that run were computed on.
    """
    from schemas.benchmark_registry import FIXTURES

    client = mlflow.tracking.MlflowClient()
    run = client.get_run(run_id)
    resolved_model = model or run.data.params.get("model_name") or "unknown"
    golds = gold_by_fixture()

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
        if example_id not in FIXTURES or example_id not in golds:
            log.warning("No fixture/gold for example '%s'; skipping.", example_id)
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
                bundle=FIXTURES[example_id],
                gold=golds[example_id],
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

    from schemas.benchmark_registry import FIXTURES

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


# =============================================================================
# Part 11 -- Integration with the existing SprintSight pipelines
# =============================================================================
#
# This module is an extension of two pipelines that already exist, not a
# replacement for either. The seams:
#
#   research/eval/runner.py   produces the candidate assessments and the
#                             per_example.jsonl rows. We CONSUME those rows
#                             (`load_records_from_run`) and layer judge
#                             columns on top via summarise_example, so the
#                             judged artifact is byte-identical to the one the
#                             harness already measured.
#
#   research/eval/
#     attach_judge_scores.py  the documented hand-off: it expects a CSV with
#                             mlflow_run_id, example_id, repeat_index,
#                             judge_quality_score, judge_rationale and merges
#                             it back into the run. `export_judge_scores`
#                             emits exactly that, so the judge_quality_score
#                             column the harness has been reserving finally
#                             gets filled and `cli.py analyze
#                             --pairwise-metric judge_quality_score` works.
#
#   research/eval/analysis.py paired_bootstrap_diff is called, not
#                             reimplemented (see paired_model_comparison).
#     metrics.py              summarise_example is the base layer of every row.
#
#   judges/run_judges.py      judges TRACES rather than stored assessments.
#                             `build_trace_scorers` wraps each rubric as an
#                             mlflow.genai.scorers scorer using the existing
#                             trace_adapters.read_candidate, so that pipeline
#                             gains the five rubric dimensions and the
#                             two-stage reasoning without being rewritten.
#     code_based_scorer.py    numeric_grade_accuracy is delegated to.
#     citation_ground_custom_judge.py
#                             its LLM grounding verdict is available as an
#                             extra column (`attach_llm_grounding`) alongside
#                             our deterministic anchor metrics.
#
#   llmops/mlflow_config.py   tracking URI + experiment creation.
#   llmops/prompt_registry.py rubric versioning (register_judge_prompts).


def _ollama_model_family(model: str) -> tuple[str | None, str | None]:
    """(family, parent_model) for an Ollama tag, or (None, None) if unknown."""
    try:
        import httpx

        base = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").replace("/v1", "")
        response = httpx.post(f"{base}/api/show", json={"name": model}, timeout=10.0)
        response.raise_for_status()
        details = response.json().get("details") or {}
        return details.get("family"), details.get("parent_model")
    except Exception:  # noqa: BLE001 - absence of Ollama is not an eval failure
        return None, None


def assert_judge_independence(
    judge_model: str,
    candidate_models: Sequence[str],
    *,
    allow_same_family: bool = ALLOW_SAME_FAMILY_JUDGE,
) -> dict[str, Any]:
    """Refuse to judge candidates from the judge's own model family.

    Self-preference bias is a measured property of LLM judges: a judge scores
    text from its own family higher than blinded human raters do. When judge
    and candidate share a family, a "better" score is not separable from "more
    like me", and the comparison cannot support a claim about quality.

    This is enforced rather than documented because the failure is silent and
    the convenient choice is always the wrong one -- the judge tag that is
    already pulled is usually a sibling of the candidates. Set
    SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE=1 only to deliberately MEASURE the
    bias, and the override is recorded as an MLflow param either way.

    Returns a provenance dict for logging. Raises when the rule is violated
    and no override is set. An unreachable Ollama downgrades to a warning:
    unknown provenance must not block a run, but it must not be silent.
    """
    judge_family, judge_parent = _ollama_model_family(judge_model)
    info: dict[str, Any] = {
        "judge_family": judge_family or "unknown",
        "judge_parent": judge_parent or "unknown",
        "same_family_override": allow_same_family,
    }

    if judge_family is None:
        log.warning(
            "Could not determine the family of judge '%s'; the "
            "self-preference check could not run. Record the judge's "
            "provenance manually in the report.",
            judge_model,
        )
        info["independence"] = "unverified"
        return info

    clashes: list[str] = []
    for candidate in sorted(set(candidate_models)):
        family, parent = _ollama_model_family(candidate)
        if family is None:
            continue
        # Same declared family, or the judge IS the candidate's base model.
        if family == judge_family or (parent and parent.split(":")[0] == judge_model.split(":")[0]):
            clashes.append(f"{candidate} (family={family}, parent={parent})")

    info["clashing_candidates"] = clashes
    info["independence"] = "ok" if not clashes else "violated"

    if clashes and not allow_same_family:
        raise RuntimeError(
            f"Judge '{judge_model}' (family={judge_family}) shares a model family "
            f"with {len(clashes)} candidate(s) under test: {', '.join(clashes)}. "
            "Self-preference bias makes these scores uninterpretable as quality. "
            "Use a judge from another family -- `ollama pull phi4:14b` or "
            "`ollama pull qwen2.5:14b-instruct` -- or set "
            "SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE=1 if you are deliberately "
            "measuring the bias itself."
        )
    if clashes:
        log.warning(
            "SAME-FAMILY JUDGING IS ACTIVE for %s. Scores are confounded with "
            "self-preference bias and must be labelled as such in the report.",
            ", ".join(clashes),
        )
    return info


# -- 11a. Hand-off to attach_judge_scores.py ---------------------------------

def export_judge_scores(
    frame: pd.DataFrame,
    path: str | Path,
    *,
    run_id: str | None = None,
    score_column: str = "judge_composite",
) -> Path:
    """Write the CSV ``research/eval/attach_judge_scores.py`` consumes.

    That script has been waiting for exactly five columns -- mlflow_run_id,
    example_id, repeat_index, judge_quality_score, judge_rationale -- and the
    model-comparison harness has been emitting ``judge_quality_score=None``
    placeholders for them since it was written. This closes that loop, which
    is what makes

        python -m research.eval.cli analyze --pairwise-metric judge_quality_score

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
        "research.eval.attach_judge_scores --judge-file %s --run-id <run_id>",
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

    ``judges/citation_ground_custom_judge.py`` already implements a careful
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

        from judges.citation_ground_custom_judge import judge_assessment
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


# -- 11c. Bridge to the trace-based pipeline in judges/ ----------------------

def build_trace_scorers(
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    metrics: Sequence[str] | None = None,
    bundle_by_team: Mapping[str, ArtifactBundle] | None = None,
    gold_by_team: Mapping[str, SprintAssessment] | None = None,
    cot_mode: Literal["two_stage", "inline"] = "two_stage",
) -> list[Any]:
    """Expose these rubrics as ``mlflow.genai.scorers`` for judges/run_judges.py.

    That pipeline judges logged TRACES, not stored assessment files, and it
    reads the candidate back with ``trace_adapters.read_candidate``. Rather
    than ask it to change, this returns scorers in the shape it already
    passes to ``mlflow.genai.evaluate(data=traces, scorers=[...])``:

        from research.eval.mlflow_judge_eval import build_trace_scorers
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

    from judges.trace_adapters import read_candidate
    from schemas.benchmark_registry import FIXTURES

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
    """Build JudgeRecords from logged traces, reusing judges/run_judges.py's
    own trace selection and candidate-reading logic.

    This is the other direction of the bridge in ``build_trace_scorers``: it
    lets the full statistical apparatus here -- calibration, position-swap
    debiasing, bootstrap CIs, the judge card -- run over traces produced by
    the live FastAPI service, not only over the research harness's stored
    assessment files.
    """
    from mlflow import MlflowClient

    from judges.trace_adapters import read_candidate
    from schemas.benchmark_registry import FIXTURES

    # Prefer judges/run_judges.py's own trace selection so both pipelines
    # select traces by identical criteria. That module is currently blocked on
    # the not-yet-added schemas/cs203_groundtruth (see the mypy override in
    # pyproject.toml), so importing it can raise ImportError through no fault
    # of ours -- hence the equivalent local fallback rather than a hard
    # dependency on a WIP module. Delete the fallback once that file lands.
    try:
        from judges.run_judges import select_traces
    except ImportError as import_error:
        # Named import_error, not error: Python unbinds an `except ... as`
        # target when the block exits, so reusing `error` for the per-trace
        # failure below would be reading a deleted variable.
        log.warning(
            "judges.run_judges is not importable (%s); using the equivalent "
            "local trace filter. Selection criteria are the same.", import_error,
        )

        def select_traces(  # type: ignore[misc]
            client, experiment_id, *, trace_ids=None, model=None, team_id=None,
            max_results=50,
        ):
            if trace_ids:
                return [client.get_trace(trace_id) for trace_id in trace_ids]
            clauses = ["trace.status = 'OK'"]
            if model:
                clauses.append(f"tags.model_name = '{model}'")
            if team_id:
                clauses.append(f"tags.team_id = '{team_id}'")
            return list(client.search_traces(
                experiment_ids=[experiment_id],
                filter_string=" AND ".join(clauses),
                max_results=max_results,
                order_by=["start_time DESC"],
            ))

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


# -- CLI ----------------------------------------------------------------------

def _print_frame(title: str, frame: pd.DataFrame) -> None:
    print(f"\n=== {title} ===")
    if frame is None or frame.empty:
        print("(empty)")
        return
    with pd.option_context("display.width", 200, "display.max_columns", 50):
        print(frame.to_string())


def _records_for_cli(arguments: argparse.Namespace) -> list[JudgeRecord]:
    if arguments.run_id:
        return load_records_from_run(
            arguments.run_id,
            model=arguments.model,
            human_annotations=arguments.human_annotations,
        )
    records = synthetic_records()
    if arguments.human_annotations:
        attach_human_annotations(records, arguments.human_annotations)
    log.warning(
            "No --run-id given: using the SYNTHETIC validation dataset. These "
            "numbers validate the pipeline and must not appear in the report."
    )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.eval.mlflow_judge_eval",
        description="MLflow-native LLM-as-a-Judge evaluation for SprintSight.",
    )
    parser.add_argument(
        "command",
        choices=["evaluate", "calibrate", "pairwise", "consistency", "compare", "selftest"],
    )
    parser.add_argument("--run-id", help="MLflow run id from research.eval.runner to judge")
    parser.add_argument("--model", help="Override the candidate model name for --run-id")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--experiment", default=JUDGE_EXPERIMENT)
    parser.add_argument("--run-name")
    parser.add_argument("--human-annotations", help="CSV of human baseline 1-5 scores")
    parser.add_argument("--metrics", nargs="*", choices=list(JUDGE_METRIC_NAMES))
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--phase", default="preliminary")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Deterministic metrics only -- no judge calls",
    )
    parser.add_argument(
        "--cot-mode",
        choices=["two_stage", "inline"],
        default="two_stage",
        help=(
            "two_stage (default) runs an evidence audit before scoring, so the "
            "score is conditioned on committed reasoning; inline is one call "
            "per cell and cannot guarantee reasoning precedes the score"
        ),
    )
    parser.add_argument(
        "--stub-judge",
        action="store_true",
        help="Use the offline stub judge (synthetic scores, for testing only)",
    )
    parser.add_argument(
        "--llm-grounding",
        action="store_true",
        help=(
            "Also run judges/citation_ground_custom_judge.py and attach its "
            "per-claim grounding verdict as extra columns"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default="research/judge_eval_report",
        help="Where to write CSV copies of the tables",
    )
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if arguments.command == "selftest":
        arguments.stub_judge = True
    if arguments.stub_judge:
        install_stub_judge()

    out_dir = Path(arguments.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        records = _records_for_cli(arguments)
        if not records:
            print("No records to evaluate.", file=sys.stderr)
            return 1

        if arguments.command in {"evaluate", "selftest"}:
            result, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                run_name=arguments.run_name,
                only_metrics=arguments.metrics,
                include_llm_metrics=not arguments.no_llm,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase="selftest" if arguments.command == "selftest" else arguments.phase,
            )
            if arguments.llm_grounding:
                # Three-way cross-check on the same citations: deterministic
                # anchors, deterministic string grounding, semantic grounding.
                frame = attach_llm_grounding(
                    frame, records, judge_model=arguments.judge_model
                )
            print("\nAggregate metrics:")
            for name, value in sorted(result.metrics.items()):
                print(f"  {name:<52} {value}")

            # Named explicitly, not by a "judge_" prefix match: summarise_example
            # contributes judge_quality_score / judge_rationale placeholder
            # columns, and a prefix match would print those empty columns as
            # though the judge had failed to score anything.
            judge_columns = [
                column
                for column in [f"judge_{name}" for name in JUDGE_METRIC_NAMES]
                + ["judge_composite"]
                if column in frame.columns
            ]
            if judge_columns:
                _print_frame(
                    "Judge scores by model",
                    frame.groupby("model")[judge_columns]
                    .apply(lambda group: group.apply(pd.to_numeric, errors="coerce").mean())
                    .round(2),
                )
            calibration = calibration_table(frame)
            _print_frame(
                "Judge calibration vs human baseline",
                calibration[
                    ["n", "quadratic_kappa", "spearman_rho", "icc_2_1",
                     "mean_signed_error", "interpretation", "warnings"]
                ].round(3),
            )
            comparison = model_comparison_report(frame)
            if not comparison.empty:
                columns = [
                    column
                    for column in ("metric", "pair", "n", "mean_diff", "ci_low",
                                   "ci_high", "cliffs_delta", "effect_magnitude",
                                   "wilcoxon_p", "p_adjusted", "min_attainable_p",
                                   "significant")
                    if column in comparison.columns
                ]
                _print_frame("Paired model comparisons (Holm-corrected)",
                             comparison[columns].round(4))
                comparison.to_csv(out_dir / "model_comparisons.csv", index=False)
            frame.to_csv(out_dir / "judge_eval_rows.csv", index=False)
            calibration.to_csv(out_dir / "judge_calibration.csv")
            if "judge_composite" in frame.columns:
                # Closes the loop with research/eval/attach_judge_scores.py,
                # which has been waiting for this file since the harness was
                # written. See export_judge_scores for the column contract.
                exported = export_judge_scores(
                    frame,
                    out_dir / "judge_scores_for_attach.csv",
                    run_id=arguments.run_id,
                )
                print(
                    "To merge these into the model-comparison run:"
                    + '\n' + "  python -m "
                    "research.eval.attach_judge_scores --judge-file "
                    f"{exported} --run-id <runner run_id>"
                )
            _print_frame("Error taxonomy", taxonomy_counts(classify_errors(frame)))

            if arguments.command == "selftest":
                return _assert_selftest_invariants(frame)
            return 0

        if arguments.command == "calibrate":
            _, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                only_metrics=arguments.metrics,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase=arguments.phase,
            )
            calibration = calibration_table(frame)
            _print_frame("Judge calibration", calibration.round(3))
            calibration.to_csv(out_dir / "judge_calibration.csv")
            print("\n" + judge_card(
                judge_model=arguments.judge_model, frame=frame, calibration=calibration
            ))
            return 0

        if arguments.command == "pairwise":
            rows, matrix, diagnostics = pairwise_tournament(
                records, judge_model=arguments.judge_model
            )
            _print_frame("Pairwise comparisons", rows)
            _print_frame("Win matrix (consistent verdicts only)", matrix)
            print("\nDiagnostics:")
            for name, value in diagnostics.items():
                print(f"  {name:<28} {value}")
            rows.to_csv(out_dir / "pairwise_comparisons.csv", index=False)
            return 0

        if arguments.command == "consistency":
            probe = self_consistency_probe(
                records,
                judge_model=arguments.judge_model,
                replicates=arguments.replicates,
                metrics=tuple(arguments.metrics or ("Code_Faithfulness",)),
            )
            _print_frame("Self-consistency", consistency_summary(probe).round(3))
            _print_frame("Perturbation sensitivity", perturbation_summary(probe).round(3))
            probe.to_csv(out_dir / "consistency_probe.csv", index=False)
            return 0

        if arguments.command == "compare":
            _, frame = run_judge_evaluation(
                records,
                judge_model=arguments.judge_model,
                experiment=arguments.experiment,
                include_llm_metrics=not arguments.no_llm,
                cot_mode=arguments.cot_mode,
                max_workers=arguments.max_workers,
                phase=arguments.phase,
            )
            comparison = model_comparison_report(frame)
            _print_frame("Paired model comparisons", comparison.round(4))
            comparison.to_csv(out_dir / "model_comparisons.csv", index=False)
            return 0

        return 1
    finally:
        if arguments.stub_judge:
            uninstall_stub_judge()


def _assert_selftest_invariants(frame: pd.DataFrame) -> int:
    """Check the framework reproduces known-answer properties of the synthetic set.

    These are the assertions a marker can run. They test the PIPELINE, not
    the models: the synthetic degraded candidate is worse by construction, so
    any failure here is a wiring bug in this module.
    """
    failures: list[str] = []

    for metric in ("Code_Faithfulness", "Evidence_Specificity"):
        column = f"judge_{metric}"
        if column not in frame.columns:
            failures.append(f"{column} missing: judge scores were not merged")
            continue
        means = frame.groupby("model")[column].apply(
            lambda series: pd.to_numeric(series, errors="coerce").mean()
        )
        if {"synthetic-faithful", "synthetic-degraded"}.issubset(means.index) and not (
            means["synthetic-faithful"] > means["synthetic-degraded"]
        ):
            failures.append(
                f"{column}: faithful ({means['synthetic-faithful']:.2f}) did not "
                f"beat degraded ({means['synthetic-degraded']:.2f})"
            )

    if "citation_anchor_rate" in frame.columns:
        degraded = frame[frame["model"] == "synthetic-degraded"]["citation_anchor_rate"]
        if degraded.notna().any():
            failures.append(
                "citation_anchor_rate should be None for the degraded candidate, "
                "whose citations were all stripped"
            )

    # The inherited columns must be present, or the summarise_example layer
    # silently stopped being wired in and the two pipelines have diverged.
    for inherited in ("groundedness_rate", "format_valid", "dimension_completion_rate"):
        if inherited not in frame.columns:
            failures.append(
                f"{inherited} missing: research.eval.metrics.summarise_example "
                "is no longer layered into build_eval_frame"
            )

    if "lint_warning_count" in frame.columns:
        by_model = frame.groupby("model")["lint_warning_count"].mean()
        if {"synthetic-faithful", "synthetic-degraded"}.issubset(by_model.index) and not (
            by_model["synthetic-degraded"] > by_model["synthetic-faithful"]
        ):
            failures.append("lint did not flag the degraded candidate more often")

    if "grade_signed_error_overall" in frame.columns:
        degraded_bias = frame[frame["model"] == "synthetic-degraded"][
            "grade_signed_error_overall"
        ].mean()
        if not degraded_bias > 0:
            failures.append(
                f"degraded candidate was built 2 points inflated but signed error "
                f"is {degraded_bias}"
            )

    print("\n=== selftest ===")
    if failures:
        for failure in failures:
            print(f"  FAIL  {failure}")
        return 1
    print("  PASS  all pipeline invariants hold on the synthetic known-answer set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
