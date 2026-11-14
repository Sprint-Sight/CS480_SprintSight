"""Server-enforced blind labelling. The single gate for AI scores and judge results.

Rules
- An instructor sees a report's AI score/judge results only after labelling all six dimensions.
- Showing them stamps report_view_log.first_score_seen_at (first exposure wins).
- Labels written after exposure are stored as is_blind=false and excluded from agreement.
- Labels lock once revealed and complete.
- Admins never label and always see everything.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.dependencies.insights import ScopedReport
from app.repositories.insights import DIMENSIONS, InsightsRepository, LabelRow
from app.repositories.interfaces import UserRecord
from app.schemas.auth import Role

REQUIRED = frozenset(DIMENSIONS)
OVERRIDE_REQUIRED = (
    "AI Insights unlock after this report's scores are saved on the Assessment Report page. "
    "Saving notifies the team's students."
)

def is_override_mode() -> bool:
    """INSIGHTS_MODE=override_gate: Insights unlock once an instructor saves an override."""
    return get_settings().insights_mode == "override_gate"

def labels_complete(labels: Iterable[LabelRow]) -> bool:
    return {label.dimension for label in labels} >= REQUIRED

def authorize_score_view(scoped: ScopedReport, insights: InsightsRepository) -> None:
    """Call before returning ANY AI score or judge result for one report."""
    if scoped.is_admin:
        return
    if is_override_mode():
        if not scoped.report.override:
            raise HTTPException(status.HTTP_409_CONFLICT, OVERRIDE_REQUIRED)
        return
    labels = insights.labels_for(scoped.report.report_id, scoped.user.id)
    if not labels_complete(labels):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Label all six dimensions before the AI results are revealed.",
        )
    insights.stamp_view(scoped.report.report_id, scoped.user.id, score_seen=True)

def visible_score_ids(
    user: UserRecord, report_ids: list[str], insights: InsightsRepository
) -> set[str]:
    """List variant of the same gate: which rows may show AI score/judge detail. Stamps them."""
    if user.role == Role.ADMIN:
        return set(report_ids)
    counts = insights.label_counts(user.id, report_ids)
    visible = {rid for rid in report_ids if counts.get(rid, 0) >= len(REQUIRED)}
    for rid in visible:
        insights.stamp_view(rid, user.id, score_seen=True)
    return visible

def stamp_evidence_view(scoped: ScopedReport, insights: InsightsRepository) -> None:
    if not scoped.is_admin:
        insights.stamp_view(scoped.report.report_id, scoped.user.id, score_seen=False)

def label_write_state(scoped: ScopedReport, insights: InsightsRepository) -> tuple[bool, bool]:
    """Returns (locked, is_blind) for a label write right now."""
    view = insights.get_view(scoped.report.report_id, scoped.user.id)
    revealed = view is not None and view.first_score_seen_at is not None
    labels = insights.labels_for(scoped.report.report_id, scoped.user.id)
    return revealed and labels_complete(labels), not revealed

def stamp_score_exposure(
    report_ids: Iterable[str], user: UserRecord, insights: InsightsRepository
) -> None:
    """Tier 2: legacy /assessments routes call this (non-blocking) so that labels written
    afterwards are marked non-blind."""
    if user.role != Role.INSTRUCTOR:
        return
    for rid in report_ids:
        insights.stamp_view(rid, user.id, score_seen=True)