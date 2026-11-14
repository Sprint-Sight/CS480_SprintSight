"""Record an instructor's override of the AI scores, for AI Insights and the MLflow sync."""

from __future__ import annotations

from app.repositories.insights import InsightsRepository, OverrideInput
from app.schemas.assessment import AssessmentReport
from app.services.insightsService.service import override_comparison


def record_override(
    report: AssessmentReport, instructor_id: str, insights: InsightsRepository | None
) -> None:
    """Called after a successful PATCH of the Assessment Report editor.

    Mode-independent, so the data is complete whichever INSIGHTS_MODE is active. Rows that did not
    change are stored too (sync_status 'not_needed'), so a later reversion can be detected.
    """
    if insights is None:
        return
    rows = [
        OverrideInput(
            dimension=row["dimension"],
            ai_score=row["ai_score"],
            override_score=row["override_score"],
            changed=row["changed"],
        )
        for row in override_comparison(report)
        if row["override_score"] is not None
    ]
    insights.upsert_overrides(report.report_id, instructor_id, rows)