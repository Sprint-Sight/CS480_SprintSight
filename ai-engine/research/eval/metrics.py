"""Judge-independent per-example metrics for the model-comparison pipeline.

These metrics do NOT need the external judge to be ready. They capture
whether the AI engine produced a parseable, well-grounded, complete
assessment at all — which is a prerequisite for the judge's work being
meaningful anyway.

Every function here takes the SprintAssessment (or lack thereof) + the
input bundle, and returns primitive values that can land directly in a
JSONL row or an MLflow metric. The output row shape is kept flat on
purpose so pandas can read it in two lines of code during analysis.
"""

from __future__ import annotations

import json

from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment
from services.grounding import find_ungrounded_citations


def _bundle_corpus(bundle: ArtifactBundle) -> str:
    # Dump the full bundle (mode="json" for datetime serialisation). The
    # per-dimension bundles the LLM actually sees are strict subsets of
    # this, so citations that are grounded in any dimension's view will be
    # grounded in this corpus too — and vice versa for the fabricated ones.
    return json.dumps(bundle.model_dump(mode="json"), ensure_ascii=True)


def groundedness_rate(bundle: ArtifactBundle, assessment: SprintAssessment) -> tuple[float, int, int]:
    """Return (rate, grounded, total). Rate is 1.0 if there are no
    citations — that is NOT "perfect grounding", it's "nothing to check";
    callers that want to count no-citations as a failure should look at
    `total` directly."""
    corpus = _bundle_corpus(bundle)
    total = 0
    ungrounded = 0
    for dim in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dim, None)
        if score is None:
            continue
        citations = score.evidence_citations or []
        total += len(citations)
        if citations:
            ungrounded += len(find_ungrounded_citations(corpus, citations))
    grounded = total - ungrounded
    rate = (grounded / total) if total else 1.0
    return rate, grounded, total


def format_validity(assessment: SprintAssessment) -> dict[str, object]:
    """Which dimensions came back scored, which failed, which were missing.

    `format_valid` is True ONLY when every dimension is present AND none is
    flagged evaluation_failed. A single-dimension failure fails the whole
    example — that's deliberate; a partial assessment with one dimension
    missing isn't usable in production either.
    """
    present = []
    failed = []
    missing = []
    for dim in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dim, None)
        if score is None:
            missing.append(dim)
            continue
        if score.evaluation_failed:
            failed.append(dim)
        else:
            present.append(dim)
    return {
        "dimensions_present": len(present),
        "dimensions_failed": len(failed),
        "dimensions_missing": len(missing),
        "dimensions_total": len(DIMENSIONS),
        "dimension_completion_rate": len(present) / len(DIMENSIONS),
        "format_valid": len(present) == len(DIMENSIONS),
        "failed_dimension_names": failed + missing,
    }


def score_summary(assessment: SprintAssessment) -> dict[str, float | None]:
    """Mean/range of rubric scores and the overall_score. Useful as a sanity
    check and for consistency SD across repeats."""
    scored = assessment.rubric_scores.scored()
    if not scored:
        return {
            "overall_score": None,
            "rubric_mean": None,
            "rubric_min": None,
            "rubric_max": None,
            "raw_rubric_average": None,
        }
    values = [s.score for s in scored]
    return {
        "overall_score": float(assessment.overall_score),
        "rubric_mean": sum(values) / len(values),
        "rubric_min": float(min(values)),
        "rubric_max": float(max(values)),
        # Unrounded average: evaluator.py rounds overall_score to 2dp, which
        # can mask tiny run-to-run variation that still matters for
        # consistency measurement.
        "raw_rubric_average": sum(values) / len(values),
    }


def per_dimension_scores(assessment: SprintAssessment) -> dict[str, float | None]:
    """Flat {dim: score_or_None} suitable for a wide-format DataFrame row."""
    out: dict[str, float | None] = {}
    for dim in DIMENSIONS:
        score = getattr(assessment.rubric_scores, dim, None)
        out[f"score_{dim}"] = float(score.score) if score and not score.evaluation_failed else None
    return out


def summarise_example(bundle: ArtifactBundle, assessment: SprintAssessment | None, error: str | None) -> dict:
    """Produce the per-example row that lands in per_example.jsonl.

    When the whole run failed (no assessment at all), everything numeric is
    None — the analysis layer treats None as a format failure, which is
    what it is.
    """
    row: dict[str, object] = {
        "format_valid": False,
        "groundedness_rate": None,
        "groundedness_citations_total": 0,
        "groundedness_citations_grounded": 0,
        "dimensions_present": 0,
        "dimensions_failed": 0,
        "dimensions_missing": len(DIMENSIONS),
        "dimensions_total": len(DIMENSIONS),
        "dimension_completion_rate": 0.0,
        "failed_dimension_names": list(DIMENSIONS),
        "overall_score": None,
        "rubric_mean": None,
        "rubric_min": None,
        "rubric_max": None,
        "raw_rubric_average": None,
        "error": error,
        # Judge slot — stays None until attach_judge_scores.py fills it in.
        "judge_quality_score": None,
        "judge_rationale": None,
    }
    if assessment is not None:
        row.update(format_validity(assessment))
        rate, grounded, total = groundedness_rate(bundle, assessment)
        row["groundedness_rate"] = rate
        row["groundedness_citations_grounded"] = grounded
        row["groundedness_citations_total"] = total
        row.update(score_summary(assessment))
    row.update(per_dimension_scores(assessment) if assessment else {f"score_{d}": None for d in DIMENSIONS})
    return row
