"""AI Insights use cases. Route handlers stay thin; everything here is testable without HTTP.

Responses use lists, never maps keyed by dimension or prompt name, so the frontend can
convert snake_case to camelCase blindly without mangling keys like `code_quality`.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from app.dependencies.insights import ScopedReport, scoped_course_ids
from app.repositories.insights import (
    DIMENSIONS,
    JUDGE_OPEN_STATUSES,
    InsightsRepository,
    LabelInput,
    RunRow,
)
from app.repositories.interfaces import ProjectRepository, UserRecord
from app.schemas.assessment import AssessmentReport
from app.schemas.auth import Role
from app.services.insightsService.blind import (
    authorize_score_view,
    is_override_mode,
    label_write_state,
    labels_complete,
    stamp_evidence_view,
    visible_score_ids,
)
from app.services.insightsService.citations import unaccepted_citations
from app.services.insightsService.judge import (
    build_tiles,
    citation_check,
    derive_judge_status,
    judge_values,
)
from app.services.insightsService.mlflow_gateway import (
    MlflowGateway,
    MlflowUnavailable,
    TraceNotFound,
)
from app.services.insightsService.trace_summary import TraceSummary

log = logging.getLogger(__name__)

CHANGE_TOLERANCE = 0.05
# Typed ManualAssessmentPatch fields are stored 0-100; testing and cicd stay 1-10 in rubric_scores.
TYPED_DIMENSIONS = frozenset(
    {"requirements", "code_quality", "testing", "documentation", "collaboration", "cicd"}
)
DIMENSION_LABELS = {
    "requirements": "Requirements",
    "code_quality": "Code Quality",
    "testing": "Testing",
    "documentation": "Documentation",
    "collaboration": "Collaboration",
    "cicd": "CI/CD",
}
# Raw evidence is not tagged per dimension; these hints say where to look for each.
DIMENSION_SOURCES = {
    "requirements": ["jira", "documents"],
    "code_quality": ["commits"],
    "testing": ["commits"],
    "documentation": ["documents", "commits"],
    "collaboration": ["peer", "commits", "jira"],
    "cicd": ["commits"],
}
NO_TRACE_NOTICE = (
    "This report has no linked MLflow trace, so trace and judge details are unavailable."
)
MLFLOW_DOWN_NOTICE = (
    "MLflow is unreachable right now. Trace and judge details will appear when it is "
    "back; the scores shown come from SprintSight."
)
TRACE_MISSING_NOTICE = "MLflow has no trace with this report's ID."
JUDGE_REFRESH_MIN_SECONDS = 10

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None

def original_ai_scores(report: AssessmentReport) -> dict[str, float] | None:
    """The AI's own per-dimension scores, without dimensions it failed to assess."""
    if report.ai_rubric_scores_original:
        return {k: float(v) for k, v in report.ai_rubric_scores_original.items() if v is not None}
    if not report.override and report.rubric_scores:
        return {
            k: float(v.score) for k, v in report.rubric_scores.items() if not v.evaluation_failed
        }
    return None # overridden before the snapshot existed: original unknown

# Current score per dimension on 0-10 scale, after any instructor overrides
def current_scores(report):
    out = {}
    for d in DIMENSIONS:
        column = getattr(report, f"{d}_score", None) if d in TYPED_DIMENSIONS else None
        if report.override and column is not None:
            out[d] = round(float(column) / 10, 2)
            continue
        detail = report.rubric_scores.get(d)
        if detail is None or (detail.evaluation_failed and not report.override):
            continue
        value = float(detail.score)
        out[d] = round(value / 10, 2) if value > 10 else value
    return out


def override_comparison(report: AssessmentReport) -> list[dict]:
    """Per dimension: the AI's original score, the current score and the adjustment (0-10)."""
    original, current = original_ai_scores(report) or {}, current_scores(report)
    rows = []
    for d in DIMENSIONS:
        ai, now = original.get(d), current.get(d)
        adjustment = round(now - ai, 2) if ai is not None and now is not None else None
        rows.append(
            {
                "dimension": d,
                "ai_score": ai,
                "override_score": now,
                "adjustment": adjustment,
                "changed": adjustment is not None and abs(adjustment) >= CHANGE_TOLERANCE,
            }
        )
    return rows

# judge status
def _store_judge(
    run: RunRow, summary: TraceSummary, insights: InsightsRepository, stale_minutes: int
) -> tuple[str, dict]:
    status_ = derive_judge_status(
        summary, run.generated_at, datetime.now(UTC), timedelta(minutes=stale_minutes)
    )
    values = judge_values(summary)
    insights.set_judge_status(run.report_id, status_, values)
    return status_, values

def refresh_judge_status(
    run: RunRow, gateway: MlflowGateway, insights: InsightsRepository, *, stale_minutes: int
) -> str:
    """Raises MlflowUnavailable; callers decide how to degrade."""
    if not run.trace_id:
        if run.judge_status != "no_trace":
            insights.set_judge_status(run.report_id, "no_trace", None)
        return "no_trace"
    try:
        summary = gateway.get_trace_summary(run.trace_id)
    except TraceNotFound:
        insights.set_judge_status(run.report_id, "no_trace", None)
        return "no_trace"
    return _store_judge(run, summary, insights, stale_minutes)[0]

def _run_item(run: RunRow, labels_done: int, score_visible: bool, unlocked: bool) -> dict:
    return {
        "report_id": run.report_id,
        "team_name": run.team_name,
        "course_id": run.course_id,
        "course_code": run.course_code,
        "section": run.section,
        "sprint_id": run.sprint_id,
        "model_name": run.model_name,
        "generated_at": _iso(run.generated_at),
        "labels_done": labels_done,
        "judge_status": run.judge_status,
        "ai_score": round(run.team_score / 10, 1) if score_visible else None,
        "ai_score_hidden": not score_visible,
        "insights_unlocked": unlocked,
        "overridden": run.overridden,
        "citation_check": citation_check(run.judge_summary) if unlocked else None,
    }

def list_runs(
    user: UserRecord,
    insights: InsightsRepository,
    projects: ProjectRepository,
    *,
    course_id: str | None,
    sprint_id: str | None,
    model: str | None,
    label_status: str,
    page: int,
    page_size: int,
) -> dict:
    runs = insights.list_runs(scoped_course_ids(user, projects))
    is_instructor = user.role == Role.INSTRUCTOR
    counts = insights.label_counts(user.id, [r.report_id for r in runs]) if is_instructor else {}

    override_mode = is_override_mode()

    def done(run: RunRow) -> int:
        if override_mode:  # "labelled" means an instructor saved an override
            return len(DIMENSIONS) if run.overridden else 0
        return min(counts.get(run.report_id, 0), len(DIMENSIONS))

    one_per_course = {r.course_id: r for r in runs}.values()
    facets = {
        "courses": sorted(
            (
                {"course_id": r.course_id, "course_code": r.course_code, "section": r.section}
                for r in one_per_course
            ),
            key=lambda c: (c["course_code"], c["section"]),
        ),
        "sprints": sorted({r.sprint_id for r in runs}),
        "models": sorted({r.model_name for r in runs}),
    }
    filtered = [
        r
        for r in runs
        if (not course_id or r.course_id == course_id)
        and (not sprint_id or r.sprint_id == sprint_id)
        and (not model or r.model_name == model)
        and (label_status == "all" or (label_status == "labelled") == (done(r) >= len(DIMENSIONS)))
    ]
    start = (page - 1) * page_size
    page_rows = filtered[start : start + page_size]
    if override_mode:
        # The AI score is no longer hidden; judge checks unlock once the report is overridden.
        is_admin = user.role == Role.ADMIN
        unlocked_ids = {r.report_id for r in page_rows if r.overridden or is_admin}
        score_ids = {r.report_id for r in page_rows}
    else:
        unlocked_ids = score_ids = visible_score_ids(
            user, [r.report_id for r in page_rows], insights
        )
    return {
        "items": [
            _run_item(r, done(r), r.report_id in score_ids, r.report_id in unlocked_ids)
            for r in page_rows
        ],
        "total": len(filtered),
        "page": page,
        "page_size": page_size,
        "facets": facets,
    }

def my_courses(
    user: UserRecord, insights: InsightsRepository, projects: ProjectRepository
) -> list[dict]:
    """Deliberately no mean AI score / flagged counts: those would leak unlabelled scores."""
    allowed = scoped_course_ids(user, projects)
    allowed_set = set(allowed) if allowed is not None else None
    courses = [c for c in projects.list_courses() if allowed_set is None or c.id in allowed_set]
    runs = insights.list_runs(allowed)
    counts = (
        insights.label_counts(user.id, [r.report_id for r in runs])
        if user.role == Role.INSTRUCTOR
        else {}
    )
    by_course: dict[str, list[RunRow]] = defaultdict(list)
    for run in runs:
        by_course[run.course_id].append(run)
    result = []
    for course in courses:
        rows = by_course.get(course.id, [])
        result.append(
            {
                "course_id": course.id,
                "code": course.code,
                "name": course.name,
                "section": course.section,
                "term": course.term,
                "year": course.year,
                "reports": len(rows),
                "labelled_by_you": sum(
                    1 for r in rows if counts.get(r.report_id, 0) >= len(DIMENSIONS)
                ),
                "overridden": sum(1 for r in rows if r.overridden),
                "judge_pending": sum(
                    1 for r in rows if r.judge_status in JUDGE_OPEN_STATUSES and r.trace_id
                ),
                "last_evaluation_at": _iso(max((r.generated_at for r in rows), default=None)),
            }
        )
    return sorted(result, key=lambda c: (c["code"], c["section"]))

# blind step to label, then reveal step to see judge & AI score
def _safe(label: str, fn, default):
    try:
        return fn()
    except Exception: # noqa: BLE001 - one missing evidence source must not break the page
        log.exception("Insights evidence source '%s' failed", label)
        return default

def evidence(
    scoped: ScopedReport,
    insights: InsightsRepository,
    metrics_repo,
    jira_repo,
    document_repo,
    peer_repo,
) -> dict:
    """Raw sprint evidence only. Never AI scores, justifications or AI-chosen citations."""
    report, run = scoped.report, scoped.run
    stamp_evidence_view(scoped, insights)
    labels = [] if scoped.is_admin else insights.labels_for(report.report_id, scoped.user.id)
    locked = True if scoped.is_admin else label_write_state(scoped, insights)[0]

    metrics = _safe(
        "metrics",
        lambda: metrics_repo.get_metrics(report.course_id, report.project_id, report.sprint_id),
        None,
    )
    commits = sorted(metrics.commits if metrics else [], key=lambda c: c.timestamp)
    jira_runs = _safe(
        "jira",
        lambda: [
            r
            for r in jira_repo.list_runs(report.project_id, report.sprint_id)
            if r.cleaned_snapshot
        ],
        [],
    )
    tickets = (
        max(jira_runs, key=lambda r: r.captured_at).cleaned_snapshot.tickets if jira_runs else []
    )
    documents = _safe("documents", lambda: document_repo.list_documents(report.project_id), [])
    peers = _safe("peer", lambda: peer_repo.list_evaluations_by_project(report.project_id), [])
    # Peer evaluations are shown under stable aliases, never names or IDs.
    people = sorted({p.rater_id for p in peers} | {p.rated_id for p in peers})
    alias = {uid: f"Member {chr(65 + i)}" for i, uid in enumerate(people)}

    return {
        "report_id": report.report_id,
        "team_name": run.team_name,
        "course_code": run.course_code,
        "section": run.section,
        "sprint_id": run.sprint_id,
        "generated_at": _iso(run.generated_at),
        "labels": [
            {
                "dimension": label.dimension,
                "score": label.score,
                "reason": label.reason,
                "sync_status": label.sync_status,
            }
            for label in labels
        ],
        "labels_done": len({label.dimension for label in labels}),
        "can_reveal": scoped.is_admin or labels_complete(labels),
        "locked": locked,
        "dimensions": [
            {"dimension": d, "label": DIMENSION_LABELS[d], "sources": DIMENSION_SOURCES[d]}
            for d in DIMENSIONS
        ],
        "metrics": None
        if metrics is None
        else {
            "commit_frequency": metrics.commit_frequency,
            "code_churn": metrics.code_churn,
            "pr_turnaround_hours": metrics.pr_turnaround_hours,
            "assigned_story_points": metrics.assigned_story_points,
            "completion_percent": metrics.completion_percent,
        },
        "commits_total": len(commits),
        "commits": [
            {
                "sha": c.sha[:12],
                "author": c.author,
                "message": c.message[:300],
                "timestamp": _iso(c.timestamp),
                "lines_added": c.lines_added,
                "lines_deleted": c.lines_deleted,
                "files_changed": len(c.files_changed),
            }
            for c in commits[:200]
        ],
        "jira": [
            {
                "key": t.ticket_id,
                "summary": t.summary,
                "status": t.status,
                "assignee": t.assignee,
                "story_points": t.story_points,
                "issue_type": t.issue_type,
            }
            for t in tickets
        ],
        "documents": [
            {"filename": d.filename, "uploaded_at": _iso(d.created_at)} for d in documents
        ],
        "peer": [
            {
                "rater": alias[p.rater_id],
                "rated": alias[p.rated_id],
                "score": p.score,
                "remarks": p.remarks,
            }
            for p in peers
        ],
    }

def save_labels(
    scoped: ScopedReport, items: list[LabelInput], insights: InsightsRepository
) -> dict:
    if scoped.user.role != Role.INSTRUCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only instructors label reports.")
    if is_override_mode():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Blind labelling is turned off (INSIGHTS_MODE=override_gate). "
            "Override the scores on the Assessment Report page instead.",
        )
    locked, is_blind = label_write_state(scoped, insights)
    if locked:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Labels are locked after the AI results were revealed."
        )
    original = original_ai_scores(scoped.report) or {}
    insights.upsert_labels(
        scoped.report.report_id,
        scoped.user.id,
        items,
        is_blind=is_blind,
        snapshots={item.dimension: original.get(item.dimension) for item in items},
    )
    labels = insights.labels_for(scoped.report.report_id, scoped.user.id)
    return {
        "labels_done": len({label.dimension for label in labels}),
        "can_reveal": labels_complete(labels),
        "is_blind": is_blind,
    }

# reveal step to see judge & AI score
def _judge_panel(
    run: RunRow, insights: InsightsRepository, gateway: MlflowGateway, stale_minutes: int
) -> tuple[dict, list[dict], str]:
    base = {
        "available": False,
        "notice": None,
        "tiles": build_tiles(run.judge_summary),
        "unaccepted_citations": [],
        "citations_truncated": False,
    }
    if not run.trace_id:
        return {**base, "notice": NO_TRACE_NOTICE}, [], "no_trace"
    try:
        summary = gateway.get_trace_summary(run.trace_id)
    except TraceNotFound:
        return {**base, "notice": TRACE_MISSING_NOTICE}, [], run.judge_status
    except MlflowUnavailable:
        # Degraded: keep cached tiles from Postgres, show the notice.
        return {**base, "notice": MLFLOW_DOWN_NOTICE}, [], run.judge_status
    status_, values = _store_judge(run, summary, insights, stale_minutes)
    rows, truncated = unaccepted_citations(summary)
    panel = {
        "available": True,
        "notice": None,
        "tiles": build_tiles(values),
        "unaccepted_citations": [asdict(r) for r in rows],
        "citations_truncated": truncated,
    }
    versions = [{"name": k, "version": v} for k, v in summary.prompt_versions.items()]
    return panel, versions, status_

def reveal( # Reveal AI's own score
    scoped: ScopedReport,
    insights: InsightsRepository,
    gateway: MlflowGateway,
    *,
    stale_minutes: int,
) -> dict:
    authorize_score_view(scoped, insights)  # THE gate
    report, run = scoped.report, scoped.run
    override_mode = is_override_mode()
    labels = (
        {}
        if scoped.is_admin or override_mode
        else {
            label.dimension: label
            for label in insights.labels_for(report.report_id, scoped.user.id)
        }
    )
    original = original_ai_scores(report) or {}
    # 0-10 for every dimension, including overridden ones (typed fields are stored 0-100).
    current = current_scores(report)
    dimensions = []
    if override_mode:
        for row in override_comparison(report):
            saved = report.override and row["override_score"] is not None
            dimensions.append(
                {
                    "dimension": row["dimension"],
                    "label": DIMENSION_LABELS[row["dimension"]],
                    "ai_score": row["ai_score"],
                    "ai_score_current": row["override_score"],
                    "overridden": row["changed"],
                    "your_score": row["override_score"] if saved else None,
                    "your_reason": None,
                    "diff": row["adjustment"] if saved else None,
                    "within_1": None,  # not a measure of accuracy: the instructor saw the AI first
                }
            )
    for d in () if override_mode else DIMENSIONS:
        ai = original.get(d, current.get(d))
        mine = labels[d].score if d in labels else None
        diff = round(mine - ai, 2) if mine is not None and ai is not None else None
        dimensions.append(
            {
                "dimension": d,
                "label": DIMENSION_LABELS[d],
                "ai_score": ai,
                "ai_score_current": current.get(d),
                "overridden": ai is not None and current.get(d) is not None and current[d] != ai,
                "your_score": mine,
                "your_reason": labels[d].reason if d in labels else None,
                "diff": diff,
                "within_1": abs(diff) <= 1 if diff is not None else None,
            }
        )
    judge, versions, status_ = _judge_panel(run, insights, gateway, stale_minutes)
    return {
        "report_id": report.report_id,
        "team_name": run.team_name,
        "course_code": run.course_code,
        "sprint_id": run.sprint_id,
        "model_name": run.model_name,
        "overall_ai_score": round(run.team_score / 10, 1),
        "judge_status": status_,
        "comparison": "override" if override_mode else "blind_label",
        "dimensions": dimensions,
        "judge": judge,
        "prompt_versions": versions,
    }

def trace_view(scoped: ScopedReport, insights: InsightsRepository, gateway: MlflowGateway) -> dict:
    authorize_score_view(scoped, insights)
    empty = {"available": False, "duration_ms": 0, "llm_call_count": 0, "spans": []}
    if not scoped.run.trace_id:
        return {**empty, "notice": NO_TRACE_NOTICE}
    try:
        summary = gateway.get_trace_summary(scoped.run.trace_id)
    except TraceNotFound:
        return {**empty, "notice": TRACE_MISSING_NOTICE}
    except MlflowUnavailable:
        return {**empty, "notice": MLFLOW_DOWN_NOTICE}
    return {
        "available": True,
        "notice": None,
        "duration_ms": summary.duration_ms,
        "llm_call_count": summary.llm_call_count,
        "spans": [asdict(s) for s in summary.spans],
    }

def judge_status_view(
    scoped: ScopedReport,
    insights: InsightsRepository,
    gateway: MlflowGateway,
    *,
    stale_minutes: int,
) -> dict:
    """Status only (no values), so it is safe before labelling. Polled every 10 s by the UI."""
    run, now = scoped.run, datetime.now(UTC)
    status_, checked = run.judge_status, run.judge_checked_at
    if checked is not None and checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    fresh = checked is not None and (now - checked).total_seconds() < JUDGE_REFRESH_MIN_SECONDS
    if status_ in JUDGE_OPEN_STATUSES and not fresh:
        try:
            status_ = refresh_judge_status(run, gateway, insights, stale_minutes=stale_minutes)
            checked = now
        except MlflowUnavailable:
            pass
    return {"report_id": run.report_id, "judge_status": status_, "checked_at": _iso(checked)}

def health(gateway: MlflowGateway, insights: InsightsRepository) -> dict:
    h = gateway.health()
    return {
        "mlflow": {
            "reachable": h.reachable,
            "server_version": h.server_version,
            "client_version": h.client_version,
            "versions_match": bool(
                h.server_version and h.client_version and h.server_version == h.client_version
            ),
        },
        "labels_pending_sync": insights.count_pending_labels(),
        "overrides_pending_sync": insights.count_pending_overrides(),
        "reports_awaiting_judge": insights.count_reports_awaiting_judge(),
        "telemetry_disabled": os.getenv("MLFLOW_DISABLE_TELEMETRY", "").strip().lower() == "true",
        "generated_at": datetime.now(UTC).isoformat(),
    }