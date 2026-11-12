"""Deterministic, LLM-free checks (Part 3): schema round trip, Python snippet syntax,
citation anchors, lint, ROUGE-L / token overlap, and arithmetic grade error against gold.
"""

from __future__ import annotations

import ast
import logging
import re
import textwrap
from collections.abc import Mapping, Sequence
from typing import Any

from evaluation.judges.grade_accuracy import numeric_grade_accuracy
from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment

log = logging.getLogger(__name__)


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


def citation_anchor_metrics(
    bundle: ArtifactBundle, assessment: SprintAssessment
) -> dict[str, Any]:
    """Evidence SPECIFICITY: do citations carry hard, checkable identifiers?

    Deliberately does NOT recompute groundedness. ``summarise_example`` in
    ``evaluation.offline.metrics`` already derives ``groundedness_rate`` from
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
# catch.


# -- 3e. Arithmetic accuracy against gold -------------------------------------

def numeric_grade_errors(
    candidate: SprintAssessment | None, gold: SprintAssessment | None
) -> dict[str, float | None]:
    """Per-dimension and overall absolute error against the gold assessment.

    Delegates to ``evaluation.judges.grade_accuracy.numeric_grade_accuracy``, the
    scorer the trace-based pipeline in ``evaluation/online/run_judges.py`` already uses,
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

    if candidate is None or gold is None:  # nothing to compare: no output, or no human gold
        for dimension in DIMENSIONS:
            out[f"grade_abs_error_{dimension}"] = None
        out["grade_mae_per_dimension"] = None
        out["grade_abs_error_overall"] = None
        out["grade_signed_error_overall"] = None
        return out

    # Same outputs shape evaluation/online/run_judges.py builds for this scorer: a
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
