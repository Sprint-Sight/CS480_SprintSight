"""LLM-as-a-Judge evaluation framework for SprintSight, built on MLflow.

This package is the *measurement* layer for the model-comparison study. It
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
config         Part 0   judge endpoint (local Ollama via MLflow's openai URI), the brace guard,
                        the single judge call, judge-independence check
specs          Parts 1-2 chain-of-thought protocol, rubric anchors, few-shot calibration, and the
                        five native MLflow GenAI metrics (make_genai_metric)
deterministic  Part 3   LLM-free checks (AST, anchors, lint, ROUGE-L, MAE)
frame          Part 4   hybrid eval frame + mlflow.evaluate() orchestration
meta           Part 5   meta-evaluation: judge-vs-human agreement (kappa, rho, alpha, ICC)
bias           Part 6   pairwise comparison with position-swap debiasing
robustness     Part 7   self-consistency and perturbation probes
inference      Part 8   paired tests, effect sizes, multiplicity
artifacts      Part 9   radar, confusion matrix, error taxonomy, judge card
records        Part 10  record loading and a stub judge so the pipeline runs without a GPU
integration    Part 11  seams to the rest of SprintSight (judge-score export, LLM grounding,
                        trace scorers for evaluation/online/run_judges.py)
cli                     python -m evaluation.offline.judge_study <command>, selftest invariants

Bootstrap CIs live in evaluation/stats.py and run provenance (git SHA, model digest) in
evaluation/offline/provenance.py, shared with the rest of the pipeline.

Two MLflow landmines this package deliberately works around
-----------------------------------------------------------
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
This package EXTENDS the two judge/eval pipelines already in the repo; it does
not replace either. ``integration`` (Part 11) holds the seams. Reused as-is, never reimplemented:
``evaluation.offline.metrics.summarise_example`` (base row), ``evaluation.stats
.paired_bootstrap_diff`` (CI), ``evaluation.judges.grade_accuracy
.numeric_grade_accuracy`` (grade error), ``evaluation.judges.trace_adapters
.read_candidate`` (trace reading), ``llmops.mlflow_config`` (tracking),
``llmops.prompt_registry`` (rubric versioning), and
``evaluation.judges.citation_grounding`` (per-claim LLM grounding).

Gaps in the current implementation that this closes:

1. One judge dimension became five. The old single-call judge (since removed) emitted
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

Two defects found while integrating, fixed outside this package:
  * ``schemas/rubrics_dimension_score._normalize_citation`` stringified an
    already-valid ``EvidenceCitation``, dropping ``reason`` and making
    the gold reference data (now ``evaluation/benchmarks/synthetic_v1.py``) raise on import.
    Nothing imported it, so it had been dead.
  * ``evaluation/online/run_judges.py`` hardcodes trace ids in ``__main__``, which are
    not valid in this checkout.

Usage
-----
    # Offline self-test of the entire pipeline (no model server needed):
    python -m evaluation.offline.judge_study selftest

    # Real run against local Ollama:
    python -m evaluation.offline.judge_study evaluate --run-id <runner run id>
"""

from evaluation.offline.judge_study.artifacts import judge_card
from evaluation.offline.judge_study.bias import pairwise_tournament
from evaluation.offline.judge_study.config import configure_judge_endpoint
from evaluation.offline.judge_study.frame import (
    JudgeRecord,
    build_deterministic_metrics,
    build_eval_frame,
    run_judge_evaluation,
)
from evaluation.offline.judge_study.inference import model_comparison_report
from evaluation.offline.judge_study.integration import build_trace_scorers
from evaluation.offline.judge_study.meta import (
    CalibrationReport,
    evaluate_judge_calibration,
)
from evaluation.offline.judge_study.records import install_stub_judge
from evaluation.offline.judge_study.robustness import self_consistency_probe
from evaluation.offline.judge_study.specs import JUDGE_METRIC_SPECS, build_genai_metrics

__all__ = [
    "JUDGE_METRIC_SPECS",
    "CalibrationReport",
    "JudgeRecord",
    "build_deterministic_metrics",
    "build_eval_frame",
    "build_genai_metrics",
    "build_trace_scorers",
    "configure_judge_endpoint",
    "evaluate_judge_calibration",
    "install_stub_judge",
    "judge_card",
    "model_comparison_report",
    "pairwise_tournament",
    "run_judge_evaluation",
    "self_consistency_probe",
]
