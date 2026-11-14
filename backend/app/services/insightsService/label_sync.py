"""The dual write: a label is saved to Postgres as `pending`, then written to MLflow as HUMAN
feedback. `find_label` runs before every first write, so a retry after a lost response never
creates a duplicate. The same loop refreshes open judge statuses, so lists never call MLflow.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta

from app.repositories.insights import InsightsRepository, LabelRow, OverrideRow, RunRow
from app.services.insightsService.mlflow_gateway import (
    OVERRIDE_PREFIX,
    MlflowGateway,
    MlflowUnavailable,
)
from app.services.insightsService.service import refresh_judge_status

log = logging.getLogger(__name__)

def sync_label(
    label: LabelRow, run: RunRow | None, insights: InsightsRepository, gateway: MlflowGateway
) -> str:
    if run is None or not run.trace_id:
        insights.mark_label_no_trace(label.label_id)
        return "no_trace"
    try:
        if label.mlflow_assessment_id:  # edited before reveal: update in place
            gateway.update_label(
                run.trace_id,
                label.mlflow_assessment_id,
                dimension=label.dimension,
                score=label.score,
                reason=label.reason,
            )
            assessment_id = label.mlflow_assessment_id
        else:  # idempotent: a previous attempt may have written it before failing
            assessment_id = gateway.find_label(run.trace_id, label.label_id) or gateway.log_label(
                run.trace_id,
                feedback_id=label.label_id,
                report_id=label.report_id,
                instructor_id=label.instructor_id,
                dimension=label.dimension,
                score=label.score,
                reason=label.reason,
                blind=label.is_blind,
            )
    except Exception as exc:  # noqa: BLE001
        insights.mark_label_failed(label.label_id, f"{type(exc).__name__}: {exc}"[:500])
        return "failed"
    insights.mark_label_synced(label.label_id, assessment_id)
    return "synced"

def sync_override(
    row: OverrideRow, run: RunRow | None, insights: InsightsRepository, gateway: MlflowGateway
) -> str:
    """Write one override to MLflow as a HUMAN assessment. Idempotent, like sync_label."""
    if run is None or not run.trace_id:
        insights.mark_override_no_trace(row.override_id)
        return "no_trace"
    try:
        if row.mlflow_assessment_id:  # value moved after the first sync: update in place
            gateway.update_label(
                run.trace_id,
                row.mlflow_assessment_id,
                dimension=row.dimension,
                score=row.override_score,
                reason=_override_reason(row),
                name_prefix=OVERRIDE_PREFIX,
            )
            assessment_id = row.mlflow_assessment_id
        else:
            assessment_id = gateway.find_label(
                run.trace_id, row.override_id, name_prefix=OVERRIDE_PREFIX
            ) or gateway.log_label(
                run.trace_id,
                feedback_id=row.override_id,
                report_id=row.report_id,
                instructor_id=row.instructor_id or "",
                dimension=row.dimension,
                score=row.override_score,
                reason=_override_reason(row),
                blind=False,  # the instructor saw the AI score before overriding
                name_prefix=OVERRIDE_PREFIX,
                extra_metadata={
                    "ai_score_original": "" if row.ai_score is None else f"{row.ai_score:g}",
                    "changed": str(row.changed).lower(),
                    "scale": "0-10",
                },
            )
    except Exception as exc:  # noqa: BLE001
        insights.mark_override_failed(row.override_id, f"{type(exc).__name__}: {exc}"[:500])
        return "failed"
    insights.mark_override_synced(row.override_id, assessment_id)
    return "synced"

def _override_reason(row: OverrideRow) -> str:
    return "Instructor override" if row.changed else "Reverted to the AI score"

def sync_pending_overrides(
    insights: InsightsRepository, gateway: MlflowGateway, *, limit: int = 50
) -> int:
    runs: dict[str, RunRow | None] = {}
    done = 0
    for row in insights.pending_overrides(limit):
        if row.report_id not in runs:
            runs[row.report_id] = insights.get_run(row.report_id)
        sync_override(row, runs[row.report_id], insights, gateway)
        done += 1
    return done

def sync_labels_for_report(
    insights: InsightsRepository, gateway: MlflowGateway, report_id: str, instructor_id: str
) -> None:
    """Runs as a FastAPI BackgroundTask right after a label save."""
    run = insights.get_run(report_id)
    for label in insights.labels_for(report_id, instructor_id):
        if label.sync_status == "pending":
            sync_label(label, run, insights, gateway)

def sync_pending_labels(
    insights: InsightsRepository,
    gateway: MlflowGateway,
    *,
    limit: int = 50,
    min_age_seconds: int = 15,
) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=min_age_seconds)
    runs: dict[str, RunRow | None] = {}
    done = 0
    for label in insights.pending_labels(limit):
        submitted = label.submitted_at
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=UTC)
        if submitted > cutoff:
            continue  # the request's own background task is probably still on it
        if label.report_id not in runs:
            runs[label.report_id] = insights.get_run(label.report_id)
        sync_label(label, runs[label.report_id], insights, gateway)
        done += 1
    return done

def refresh_open_judges(
    insights: InsightsRepository, gateway: MlflowGateway, *, stale_minutes: int, limit: int = 20
) -> None:
    for run in insights.runs_needing_judge_refresh(limit):
        try:
            refresh_judge_status(run, gateway, insights, stale_minutes=stale_minutes)
        except MlflowUnavailable:
            return  # MLflow down: try again next tick
        except Exception:  # noqa: BLE001
            log.exception("Judge status refresh failed for report %s", run.report_id)

class LabelSyncWorker:
    """Mirrors notificationService.queue.EmailDispatcher."""

    def __init__(
        self,
        insights: InsightsRepository,
        gateway: MlflowGateway,
        interval_seconds: float,
        stale_minutes: int,
    ) -> None:
        self._insights, self._gateway = insights, gateway
        self._interval = max(2.0, interval_seconds)
        self._stale_minutes = stale_minutes
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="insights-label-sync", daemon=True)
        self._thread.start()
        log.info("Insights label sync started (every %ss).", self._interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                sync_pending_labels(self._insights, self._gateway)
                sync_pending_overrides(self._insights, self._gateway)
                refresh_open_judges(
                    self._insights, self._gateway, stale_minutes=self._stale_minutes
                )
            except Exception:  # noqa: BLE001 - never let the worker die
                log.exception("Insights sync tick failed")
            self._stop.wait(self._interval)