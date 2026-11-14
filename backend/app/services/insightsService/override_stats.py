"""Override statistics for INSIGHTS_MODE=override_gate.

These describe how often and how far instructors changed AI scores. They are NOT a measure of AI
accuracy: the instructor saw the AI score first, so a small adjustment may just be anchoring, and a
report nobody saved is not evidence of agreement. Exact-match and within-1 rates are deliberately
not computed.
"""

from __future__ import annotations

from app.repositories.insights import DIMENSIONS
from app.schemas.assessment import AssessmentReport
from app.services.insightsService.service import (
    CHANGE_TOLERANCE,
    original_ai_scores,
    override_comparison,
)

NOTICE = (
    "Overrides are not blind: the instructor saw the AI score first. These figures show how often "
    "and how far instructors changed AI scores. They are not a measure of AI accuracy, and "
    "reports nobody saved are not counted as agreement."
)
DIRECTION_THRESHOLD = 0.25  # mean signed adjustment (0-10 scale) below which direction is "mixed"

def override_stats(reports: list[AssessmentReport]) -> dict:
    # Only reports with a known AI baseline can be compared.
    eligible = [r for r in reports if original_ai_scores(r)]
    saved = [r for r in eligible if r.override]
    adjustments: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
    reports_with_changes = 0
    for report in saved:
        rows = [r for r in override_comparison(report) if r["adjustment"] is not None]
        for row in rows:
            adjustments[row["dimension"]].append(row["adjustment"])
        reports_with_changes += any(row["changed"] for row in rows)

    by_dimension = []
    for d in DIMENSIONS:
        values = adjustments[d]
        changed = [a for a in values if abs(a) >= CHANGE_TOLERANCE]
        mean = round(sum(changed) / len(changed), 2) if changed else None
        if mean is None:
            direction = None
        elif mean >= DIRECTION_THRESHOLD:
            direction = "raised"
        elif mean <= -DIRECTION_THRESHOLD:
            direction = "lowered"
        else:
            direction = "mixed"
        by_dimension.append(
            {
                "dimension": d,
                "overrides_saved": len(values),
                "changed": len(changed),
                "change_rate": round(len(changed) / len(values), 3) if values else None,
                "mean_adjustment": mean,  # signed, over changed rows only
                "mean_abs_adjustment": (
                    round(sum(abs(a) for a in changed) / len(changed), 2) if changed else None
                ),
                "direction": direction,
            }
        )
    return {
        "reports": len(eligible),
        "reports_overridden": len(saved),
        "override_rate": round(len(saved) / len(eligible), 3) if eligible else None,
        "reports_with_changes": reports_with_changes,
        "by_dimension": by_dimension,
        "notice": NOTICE,
    }