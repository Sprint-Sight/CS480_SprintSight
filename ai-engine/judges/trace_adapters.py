import logging
from typing import cast

from mlflow.entities import Trace
from pydantic import ValidationError

from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import (
    DimensionName,
    ModelOutput,
    RubricDimensionScore,
)
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment
from services.grounding import find_ungrounded_citations

log = logging.getLogger(__name__)


def read_candidate(trace: Trace, bundle: ArtifactBundle | None = None) -> tuple[RubricsScore, int]:
    """Returns (rubric_scores, citations_dropped_by_code) for a logged trace.

    New format (evaluator stores the assessment on the root span): read it directly.
    Old format: rebuild each dimension from the raw model response under its
    `Evaluate_Dimension_<dim>` span, then apply the same fabricated-identifier filter the
    pipeline applies (needs `bundle`; skipped when None). Failed dimensions stay None."""
    spans = trace.data.spans
    root = next(s for s in spans if s.parent_id is None)

    if isinstance(root.outputs, dict) and "rubric_scores" in root.outputs:
        return SprintAssessment.model_validate(root.outputs).rubric_scores, 0

    by_id = {s.span_id: s for s in spans}
    final: dict[str, ModelOutput] = {}
    for s in spans:
        parent = by_id.get(s.parent_id) if s.parent_id is not None else None
        if s.name != "AsyncCompletions" or parent is None or not parent.name.startswith("Evaluate_Dimension_"):
            continue
        try:
            mo = ModelOutput.model_validate_json(s.outputs["choices"][0]["message"]["content"])
        except (ValidationError, KeyError, IndexError, TypeError) as exc:
            # An attempt that failed schema validation, or whose trace payload was
            # malformed; it was retried, so skip it and let a later valid attempt win.
            log.debug("Skipping dimension attempt in span %s: %s", s.span_id, exc)
            continue
        final[parent.name.removeprefix("Evaluate_Dimension_")] = mo   # a later valid attempt overwrites

    bundle_json = bundle.model_dump_json() if bundle else None
    dropped, scores = 0, {}
    for dim, mo in final.items():
        data = mo.model_dump()
        if bundle_json:
            bad = find_ungrounded_citations(bundle_json, mo.evidence_citations)
            dropped += len(bad)
            data["evidence_citations"] = [c.model_dump() for c in mo.evidence_citations if c not in bad]
        scores[dim] = RubricDimensionScore(dimension=cast(DimensionName, dim), **data)
    return RubricsScore(**scores), dropped
