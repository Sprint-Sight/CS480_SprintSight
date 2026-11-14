"""Persistence for AI Insights.

Postgres is the index: which report has which MLflow trace, the cached judge status,
who has seen AI results (blind labelling), and instructor labels. MLflow is only ever
read by an explicit trace ID taken from these rows, never searched from user input.

The trace link itself is `assessment_reports.trace_id`, written by the assessment flow
(see PostgresAssessmentRepository.save_report); this module only reads it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

DIMENSIONS: tuple[str, ...] = (
    "requirements",
    "code_quality",
    "testing",
    "documentation",
    "collaboration",
    "cicd",
)
JUDGE_OPEN_STATUSES = ("unknown", "pending")
# The ai-engine's judge queue retries transient failures (Ollama down, a timeout) and a re-run
# replaces the failed assessments, so a recent 'failed' is re-checked for this long.
JUDGE_FAILED_RECHECK_HOURS = 24
MAX_SYNC_ATTEMPTS = 10

def canonical_report_id(report_id: str) -> str:
    """Reports are created as 'rpt-<uuid>' but stored as a bare UUID in Postgres."""
    return report_id.removeprefix("rpt-")

def _uuid(value: str) -> UUID | None:
    try:
        return UUID(canonical_report_id(value))
    except (ValueError, AttributeError):
        return None

@dataclass(frozen=True)
class RunRow:
    report_id: str
    course_id: str
    course_code: str
    course_name: str
    section: str
    project_id: str
    team_name: str
    sprint_id: str
    model_name: str
    generated_at: datetime
    team_score: float  # 0-100 as stored by the backend
    trace_id: str | None  # MLflow trace of the grading run
    judge_status: str
    judge_checked_at: datetime | None
    judge_summary: dict | None
    overridden: bool = False  # an instructor saved the Assessment Report editor

@dataclass(frozen=True)
class LabelInput:
    dimension: str
    score: int
    reason: str | None

@dataclass(frozen=True)
class LabelRow:
    label_id: str
    report_id: str
    instructor_id: str
    dimension: str
    score: int
    reason: str | None
    ai_score_snapshot: float | None
    is_blind: bool
    submitted_at: datetime
    sync_status: str
    mlflow_assessment_id: str | None
    sync_attempts: int
    last_sync_error: str | None

@dataclass(frozen=True)
class OverrideInput:
    dimension: str
    ai_score: float | None  # 0-10 snapshot; None when the AI did not assess it
    override_score: float  # 0-10
    changed: bool

@dataclass(frozen=True)
class OverrideRow:
    override_id: str
    report_id: str
    instructor_id: str | None
    dimension: str
    ai_score: float | None
    override_score: float
    changed: bool
    sync_status: str
    mlflow_assessment_id: str | None
    sync_attempts: int
    last_sync_error: str | None

@dataclass(frozen=True)
class ViewRow:
    first_viewed_at: datetime
    first_score_seen_at: datetime | None

class InsightsRepository(Protocol):
    def list_runs(self, course_ids: list[str] | None) -> list[RunRow]: ...
    def get_run(self, report_id: str) -> RunRow | None: ...
    def runs_needing_judge_refresh(self, limit: int) -> list[RunRow]: ...
    def set_judge_status(self, report_id: str, status: str, summary: dict | None) -> None: ...
    def count_reports_awaiting_judge(self) -> int: ...
    def labels_for(self, report_id: str, instructor_id: str) -> list[LabelRow]: ...
    def label_counts(self, instructor_id: str, report_ids: list[str]) -> dict[str, int]: ...
    def upsert_labels(
        self,
        report_id: str,
        instructor_id: str,
        items: Iterable[LabelInput],
        *,
        is_blind: bool,
        snapshots: dict[str, float | None],
    ) -> None: ...
    def pending_labels(self, limit: int) -> list[LabelRow]: ...
    def mark_label_synced(self, label_id: str, assessment_id: str) -> None: ...
    def mark_label_failed(self, label_id: str, error: str) -> None: ...
    def mark_label_no_trace(self, label_id: str) -> None: ...
    def count_pending_labels(self) -> int: ...
    def stamp_view(self, report_id: str, user_id: str, *, score_seen: bool) -> ViewRow: ...
    def get_view(self, report_id: str, user_id: str) -> ViewRow | None: ...
    def upsert_overrides(
        self, report_id: str, instructor_id: str, rows: Iterable[OverrideInput]
    ) -> None: ...
    def pending_overrides(self, limit: int) -> list[OverrideRow]: ...
    def mark_override_synced(self, override_id: str, assessment_id: str) -> None: ...
    def mark_override_failed(self, override_id: str, error: str) -> None: ...
    def mark_override_no_trace(self, override_id: str) -> None: ...
    def count_pending_overrides(self) -> int: ...

# SCHEMA
# Mirrored at the end of backend/init.sql. Every statement is idempotent: this runs on
# every backend start. assessment_reports.trace_id is created by ensure_assessment_schema.
_SCHEMA_STATEMENTS = (
    "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS ai_rubric_scores_original JSONB",
    """ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS judge_status VARCHAR(16) NOT NULL
       DEFAULT 'unknown'
       CHECK (judge_status IN ('unknown','pending','complete','failed','stale','no_trace'))""",
    "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS judge_checked_at TIMESTAMPTZ",
    "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS judge_summary JSONB",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_reports_trace
       ON assessment_reports(trace_id) WHERE trace_id IS NOT NULL""",
    # Backfill: never-overridden reports still hold the AI's original scores. A dimension
    # the AI failed to assess carries a placeholder score, so it is left out.
    """UPDATE assessment_reports
       SET ai_rubric_scores_original = (
           SELECT jsonb_object_agg(key, (value->>'score')::numeric)
           FROM jsonb_each(rubric_scores)
           WHERE NOT COALESCE((value->>'evaluation_failed')::boolean, FALSE))
       WHERE ai_rubric_scores_original IS NULL AND override = FALSE
         AND rubric_scores <> '{}'::jsonb""",
    """UPDATE assessment_reports SET judge_status = 'no_trace'
       WHERE trace_id IS NULL AND judge_status = 'unknown'""",
    """CREATE TABLE IF NOT EXISTS report_view_log (
        report_id UUID NOT NULL REFERENCES assessment_reports(report_id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        first_viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        first_score_seen_at TIMESTAMPTZ,
        PRIMARY KEY (report_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS instructor_labels (
        label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        report_id UUID NOT NULL REFERENCES assessment_reports(report_id) ON DELETE CASCADE,
        instructor_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        dimension VARCHAR(32) NOT NULL CHECK (dimension IN
            ('requirements','code_quality','testing','documentation','collaboration','cicd')),
        score SMALLINT NOT NULL CHECK (score BETWEEN 1 AND 10),
        reason VARCHAR(1000),
        ai_score_snapshot NUMERIC(4, 2),
        is_blind BOOLEAN NOT NULL,
        submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        sync_status VARCHAR(10) NOT NULL DEFAULT 'pending'
            CHECK (sync_status IN ('pending','synced','failed','no_trace')),
        mlflow_assessment_id VARCHAR(64),
        sync_attempts INTEGER NOT NULL DEFAULT 0,
        last_sync_error TEXT,
        UNIQUE (report_id, instructor_id, dimension))""",
    """CREATE INDEX IF NOT EXISTS idx_instructor_labels_sync
       ON instructor_labels(sync_status, submitted_at)""",
    """CREATE INDEX IF NOT EXISTS idx_instructor_labels_instructor
       ON instructor_labels(instructor_id, submitted_at DESC)""",
    # Override gate mode: one row per report and dimension, 0-10 scale, one decimal.
    """CREATE TABLE IF NOT EXISTS report_overrides (
        override_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        report_id UUID NOT NULL REFERENCES assessment_reports(report_id) ON DELETE CASCADE,
        dimension VARCHAR(32) NOT NULL CHECK (dimension IN
            ('requirements','code_quality','testing','documentation','collaboration','cicd')),
        instructor_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
        ai_score NUMERIC(4, 2),
        override_score NUMERIC(4, 2) NOT NULL CHECK (override_score BETWEEN 0 AND 10),
        changed BOOLEAN NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        sync_status VARCHAR(12) NOT NULL DEFAULT 'not_needed'
            CHECK (sync_status IN ('pending','synced','failed','no_trace','not_needed')),
        mlflow_assessment_id VARCHAR(64),
        sync_attempts INTEGER NOT NULL DEFAULT 0,
        last_sync_error TEXT,
        UNIQUE (report_id, dimension))""",
    """CREATE INDEX IF NOT EXISTS idx_report_overrides_sync
       ON report_overrides(sync_status, updated_at)""",
)


def ensure_insights_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)


# ----------------------------------------------------------------- Postgres
_RUN_SELECT = """
SELECT r.report_id, r.course_id, c.code AS course_code, c.name AS course_name, c.section,
       r.project_id, p.team_name, r.sprint_id, r.model_name, r.generated_at,
       COALESCE((r.team_score->>'score')::float, 0) AS team_score,
       r.trace_id, r.judge_status, r.judge_checked_at, r.judge_summary,
       r.override AS overridden
FROM assessment_reports r
JOIN projects p ON p.project_id = r.project_id
JOIN courses c ON c.course_id = r.course_id"""

def _run(row: dict) -> RunRow:
    return RunRow(
        report_id=str(row["report_id"]),
        course_id=str(row["course_id"]),
        course_code=row["course_code"],
        course_name=row["course_name"],
        section=row["section"],
        project_id=str(row["project_id"]),
        team_name=row["team_name"],
        sprint_id=row["sprint_id"],
        model_name=row["model_name"],
        generated_at=row["generated_at"],
        team_score=float(row["team_score"] or 0),
        trace_id=row["trace_id"],
        judge_status=row["judge_status"],
        judge_checked_at=row["judge_checked_at"],
        judge_summary=row["judge_summary"],
        overridden=bool(row["overridden"]),
    )

def _label(row: dict) -> LabelRow:
    snapshot = row["ai_score_snapshot"]
    return LabelRow(
        label_id=str(row["label_id"]),
        report_id=str(row["report_id"]),
        instructor_id=str(row["instructor_id"]),
        dimension=row["dimension"],
        score=int(row["score"]),
        reason=row["reason"],
        ai_score_snapshot=float(snapshot) if snapshot is not None else None,
        is_blind=row["is_blind"],
        submitted_at=row["submitted_at"],
        sync_status=row["sync_status"],
        mlflow_assessment_id=row["mlflow_assessment_id"],
        sync_attempts=row["sync_attempts"],
        last_sync_error=row["last_sync_error"],
    )

def _override(row: dict) -> OverrideRow:
    ai = row["ai_score"]
    return OverrideRow(
        override_id=str(row["override_id"]),
        report_id=str(row["report_id"]),
        instructor_id=str(row["instructor_id"]) if row["instructor_id"] else None,
        dimension=row["dimension"],
        ai_score=float(ai) if ai is not None else None,
        override_score=float(row["override_score"]),
        changed=bool(row["changed"]),
        sync_status=row["sync_status"],
        mlflow_assessment_id=row["mlflow_assessment_id"],
        sync_attempts=row["sync_attempts"],
        last_sync_error=row["last_sync_error"],
    )

class PostgresInsightsRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def list_runs(self, course_ids: list[str] | None) -> list[RunRow]:
        if course_ids is not None and not course_ids:
            return []
        with self._pool.connection() as connection:
            if course_ids is None:
                rows = connection.execute(_RUN_SELECT + " ORDER BY r.generated_at DESC").fetchall()
            else:
                ids = [u for u in (_uuid(c) for c in course_ids) if u]
                rows = connection.execute(
                    _RUN_SELECT + " WHERE r.course_id = ANY(%s) ORDER BY r.generated_at DESC",
                    (ids,),
                ).fetchall()
        return [_run(row) for row in rows]

    def get_run(self, report_id: str) -> RunRow | None:
        rid = _uuid(report_id)
        if rid is None:
            return None
        with self._pool.connection() as connection:
            row = connection.execute(_RUN_SELECT + " WHERE r.report_id = %s", (rid,)).fetchone()
        return _run(row) if row else None

    def runs_needing_judge_refresh(self, limit: int) -> list[RunRow]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                _RUN_SELECT + " WHERE r.judge_status IN ('unknown','pending')"
                " OR (r.judge_status = 'failed'"
                "     AND r.generated_at > now() - make_interval(hours => %s))"
                " ORDER BY r.generated_at DESC LIMIT %s",
                (JUDGE_FAILED_RECHECK_HOURS, limit),
            ).fetchall()
        return [_run(row) for row in rows]

    def set_judge_status(self, report_id: str, status: str, summary: dict | None) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE assessment_reports SET judge_status = %s, judge_checked_at = now(),
                   judge_summary = COALESCE(%s::jsonb, judge_summary) WHERE report_id = %s""",
                (status, Json(summary) if summary is not None else None, _uuid(report_id)),
            )

    def count_reports_awaiting_judge(self) -> int:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT count(*) AS n FROM assessment_reports
                   WHERE judge_status IN ('unknown','pending') AND trace_id IS NOT NULL"""
            ).fetchone()
        return int(row["n"])

    def labels_for(self, report_id: str, instructor_id: str) -> list[LabelRow]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM instructor_labels WHERE report_id = %s AND instructor_id = %s
                   ORDER BY dimension""",
                (_uuid(report_id), _uuid(instructor_id)),
            ).fetchall()
        return [_label(row) for row in rows]

    def label_counts(self, instructor_id: str, report_ids: list[str]) -> dict[str, int]:
        ids = [u for u in (_uuid(r) for r in report_ids) if u]
        if not ids:
            return {}
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT report_id, count(*) AS n FROM instructor_labels
                   WHERE instructor_id = %s AND report_id = ANY(%s) GROUP BY report_id""",
                (_uuid(instructor_id), ids),
            ).fetchall()
        return {str(row["report_id"]): int(row["n"]) for row in rows}

    def upsert_labels(
        self,
        report_id: str,
        instructor_id: str,
        items: Iterable[LabelInput],
        *,
        is_blind: bool,
        snapshots: dict[str, float | None],
    ) -> None:
        rid, uid = _uuid(report_id), _uuid(instructor_id)
        with self._pool.connection() as connection, connection.transaction():
            for item in items:
                connection.execute(
                    """INSERT INTO instructor_labels
                       (report_id, instructor_id, dimension, score, reason,
                        ai_score_snapshot, is_blind)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (report_id, instructor_id, dimension) DO UPDATE SET
                         score = EXCLUDED.score, reason = EXCLUDED.reason,
                         ai_score_snapshot = EXCLUDED.ai_score_snapshot,
                         is_blind = EXCLUDED.is_blind,
                         submitted_at = now(), sync_status = 'pending',
                         sync_attempts = 0, last_sync_error = NULL""",
                    (
                        rid,
                        uid,
                        item.dimension,
                        item.score,
                        item.reason,
                        snapshots.get(item.dimension),
                        is_blind,
                    ),
                )

    def pending_labels(self, limit: int) -> list[LabelRow]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM instructor_labels WHERE sync_status = 'pending'
                   ORDER BY submitted_at LIMIT %s""",
                (limit,),
            ).fetchall()
        return [_label(row) for row in rows]

    def mark_label_synced(self, label_id: str, assessment_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE instructor_labels SET sync_status = 'synced', mlflow_assessment_id = %s,
                   last_sync_error = NULL WHERE label_id = %s""",
                (assessment_id, UUID(label_id)),
            )

    def mark_label_failed(self, label_id: str, error: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE instructor_labels
                   SET sync_attempts = sync_attempts + 1, last_sync_error = %s,
                       sync_status = CASE WHEN sync_attempts + 1 >= %s
                                          THEN 'failed' ELSE 'pending' END
                   WHERE label_id = %s""",
                (error, MAX_SYNC_ATTEMPTS, UUID(label_id)),
            )

    def mark_label_no_trace(self, label_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "UPDATE instructor_labels SET sync_status = 'no_trace' WHERE label_id = %s",
                (UUID(label_id),),
            )

    def count_pending_labels(self) -> int:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT count(*) AS n FROM instructor_labels WHERE sync_status = 'pending'"
            ).fetchone()
        return int(row["n"])

    def stamp_view(self, report_id: str, user_id: str, *, score_seen: bool) -> ViewRow:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO report_view_log (report_id, user_id, first_score_seen_at)
                   VALUES (%s, %s, CASE WHEN %s THEN now() END)
                   ON CONFLICT (report_id, user_id) DO UPDATE SET first_score_seen_at =
                     COALESCE(report_view_log.first_score_seen_at, EXCLUDED.first_score_seen_at)
                   RETURNING first_viewed_at, first_score_seen_at""",
                (_uuid(report_id), _uuid(user_id), score_seen),
            ).fetchone()
        return ViewRow(row["first_viewed_at"], row["first_score_seen_at"])

    def get_view(self, report_id: str, user_id: str) -> ViewRow | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT first_viewed_at, first_score_seen_at FROM report_view_log
                   WHERE report_id = %s AND user_id = %s""",
                (_uuid(report_id), _uuid(user_id)),
            ).fetchone()
        return ViewRow(row["first_viewed_at"], row["first_score_seen_at"]) if row else None

    def upsert_overrides(
        self, report_id: str, instructor_id: str, rows: Iterable[OverrideInput]
    ) -> None:
        rid, uid = _uuid(report_id), _uuid(instructor_id)
        with self._pool.connection() as connection, connection.transaction():
            for row in rows:
                connection.execute(
                    """INSERT INTO report_overrides
                       (report_id, dimension, instructor_id, ai_score, override_score, changed,
                        sync_status)
                       VALUES (%s, %s, %s, %s, %s, %s,
                               CASE WHEN %s THEN 'pending' ELSE 'not_needed' END)
                       ON CONFLICT (report_id, dimension) DO UPDATE SET
                         instructor_id = EXCLUDED.instructor_id,
                         ai_score = EXCLUDED.ai_score,
                         changed = EXCLUDED.changed,
                         updated_at = now(),
                         last_sync_error = NULL,
                         sync_attempts = 0,
                         sync_status = CASE
                           WHEN report_overrides.override_score IS NOT DISTINCT FROM
                                EXCLUDED.override_score THEN report_overrides.sync_status
                           WHEN EXCLUDED.changed
                                OR report_overrides.mlflow_assessment_id IS NOT NULL THEN 'pending'
                           ELSE 'not_needed' END,
                         override_score = EXCLUDED.override_score""",
                    (
                        rid,
                        row.dimension,
                        uid,
                        row.ai_score,
                        row.override_score,
                        row.changed,
                        row.changed,
                    ),
                )

    def pending_overrides(self, limit: int) -> list[OverrideRow]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM report_overrides WHERE sync_status = 'pending'
                   ORDER BY updated_at LIMIT %s""",
                (limit,),
            ).fetchall()
        return [_override(row) for row in rows]

    def mark_override_synced(self, override_id: str, assessment_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE report_overrides SET sync_status = 'synced', mlflow_assessment_id = %s,
                   last_sync_error = NULL WHERE override_id = %s""",
                (assessment_id, UUID(override_id)),
            )

    def mark_override_failed(self, override_id: str, error: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE report_overrides
                   SET sync_attempts = sync_attempts + 1, last_sync_error = %s,
                       sync_status = CASE WHEN sync_attempts + 1 >= %s
                                          THEN 'failed' ELSE 'pending' END
                   WHERE override_id = %s""",
                (error, MAX_SYNC_ATTEMPTS, UUID(override_id)),
            )

    def mark_override_no_trace(self, override_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "UPDATE report_overrides SET sync_status = 'no_trace' WHERE override_id = %s",
                (UUID(override_id),),
            )

    def count_pending_overrides(self) -> int:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT count(*) AS n FROM report_overrides WHERE sync_status = 'pending'"
            ).fetchone()
        return int(row["n"])

# in-memory (tests)
class InMemoryInsightsRepository:
    """Test double that reads reports/projects from the in-memory repositories it wraps."""

    def __init__(self, assessments, projects) -> None:
        self._assessments = assessments
        self._projects = projects
        self._judge: dict[str, tuple[str, datetime | None, dict | None]] = {}
        self._labels: dict[tuple[str, str, str], LabelRow] = {}
        self._views: dict[tuple[str, str], ViewRow] = {}
        self._overrides: dict[tuple[str, str], OverrideRow] = {}

    def _to_run(self, report) -> RunRow:
        project = self._projects.get_project(report.project_id)
        course = self._projects.get_course(report.course_id)
        default = "unknown" if report.trace_id else "no_trace"
        status, checked, summary = self._judge.get(report.report_id, (default, None, None))
        return RunRow(
            report_id=report.report_id,
            course_id=report.course_id,
            course_code=course.code if course else (project.course_code if project else ""),
            course_name=course.name if course else "",
            section=course.section if course else "",
            project_id=report.project_id,
            team_name=project.team_name if project else report.project_id,
            sprint_id=report.sprint_id,
            model_name=report.model_name,
            generated_at=report.generated_at,
            team_score=float(report.team_score.score),
            trace_id=report.trace_id,
            judge_status=status,
            judge_checked_at=checked,
            judge_summary=summary,
            overridden=bool(report.override),
        )

    def list_runs(self, course_ids):
        reports = list(self._assessments._reports.values())  # test double: private access is fine
        runs = [self._to_run(r) for r in reports if course_ids is None or r.course_id in course_ids]
        return sorted(runs, key=lambda run: run.generated_at, reverse=True)

    def get_run(self, report_id):
        report = self._assessments.get_report(report_id)
        return self._to_run(report) if report else None

    def runs_needing_judge_refresh(self, limit):
        recent = datetime.now(UTC) - timedelta(hours=JUDGE_FAILED_RECHECK_HOURS)

        def due(run: RunRow) -> bool:
            if run.judge_status in JUDGE_OPEN_STATUSES:
                return True
            generated = run.generated_at
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=UTC)
            return run.judge_status == "failed" and generated > recent

        return [run for run in self.list_runs(None) if due(run)][:limit]

    def set_judge_status(self, report_id, status, summary):
        previous = self._judge.get(report_id)
        kept = summary if summary is not None else (previous[2] if previous else None)
        self._judge[report_id] = (status, datetime.now(UTC), kept)

    def count_reports_awaiting_judge(self):
        return sum(
            1
            for run in self.list_runs(None)
            if run.judge_status in JUDGE_OPEN_STATUSES and run.trace_id
        )

    def labels_for(self, report_id, instructor_id):
        return sorted(
            (
                label
                for (rid, uid, _), label in self._labels.items()
                if rid == report_id and uid == instructor_id
            ),
            key=lambda label: label.dimension,
        )

    def label_counts(self, instructor_id, report_ids):
        wanted, counts = set(report_ids), {}
        for rid, uid, _ in self._labels:
            if uid == instructor_id and rid in wanted:
                counts[rid] = counts.get(rid, 0) + 1
        return counts

    def upsert_labels(self, report_id, instructor_id, items, *, is_blind, snapshots):
        for item in items:
            key = (report_id, instructor_id, item.dimension)
            existing = self._labels.get(key)
            self._labels[key] = LabelRow(
                label_id=existing.label_id if existing else str(uuid4()),
                report_id=report_id,
                instructor_id=instructor_id,
                dimension=item.dimension,
                score=item.score,
                reason=item.reason,
                ai_score_snapshot=snapshots.get(item.dimension),
                is_blind=is_blind,
                submitted_at=datetime.now(UTC),
                sync_status="pending",
                mlflow_assessment_id=existing.mlflow_assessment_id if existing else None,
                sync_attempts=0,
                last_sync_error=None,
            )

    def _update_label(self, label_id, **changes):
        for key, label in self._labels.items():
            if label.label_id == label_id:
                self._labels[key] = replace(label, **changes)
                return

    def pending_labels(self, limit):
        pending = [label for label in self._labels.values() if label.sync_status == "pending"]
        return sorted(pending, key=lambda label: label.submitted_at)[:limit]

    def mark_label_synced(self, label_id, assessment_id):
        self._update_label(
            label_id, sync_status="synced", mlflow_assessment_id=assessment_id, last_sync_error=None
        )

    def mark_label_failed(self, label_id, error):
        label = next(label for label in self._labels.values() if label.label_id == label_id)
        attempts = label.sync_attempts + 1
        self._update_label(
            label_id,
            sync_attempts=attempts,
            last_sync_error=error,
            sync_status="failed" if attempts >= MAX_SYNC_ATTEMPTS else "pending",
        )

    def mark_label_no_trace(self, label_id):
        self._update_label(label_id, sync_status="no_trace")

    def count_pending_labels(self):
        return sum(1 for label in self._labels.values() if label.sync_status == "pending")

    def stamp_view(self, report_id, user_id, *, score_seen):
        now = datetime.now(UTC)
        existing = self._views.get((report_id, user_id))
        view = ViewRow(
            first_viewed_at=existing.first_viewed_at if existing else now,
            first_score_seen_at=(existing.first_score_seen_at if existing else None)
            or (now if score_seen else None),
        )
        self._views[(report_id, user_id)] = view
        return view

    def get_view(self, report_id, user_id):
        return self._views.get((report_id, user_id))

    def upsert_overrides(self, report_id, instructor_id, rows):
        for row in rows:
            key = (report_id, row.dimension)
            existing = self._overrides.get(key)
            if existing is None:
                status = "pending" if row.changed else "not_needed"
            elif existing.override_score == row.override_score:
                status = existing.sync_status
            elif row.changed or existing.mlflow_assessment_id:
                status = "pending"
            else:
                status = "not_needed"
            self._overrides[key] = OverrideRow(
                override_id=existing.override_id if existing else str(uuid4()),
                report_id=report_id,
                instructor_id=instructor_id,
                dimension=row.dimension,
                ai_score=row.ai_score,
                override_score=row.override_score,
                changed=row.changed,
                sync_status=status,
                mlflow_assessment_id=existing.mlflow_assessment_id if existing else None,
                sync_attempts=0,
                last_sync_error=None,
            )

    def overrides_for(self, report_id):
        return sorted(
            (o for (rid, _), o in self._overrides.items() if rid == report_id),
            key=lambda o: o.dimension,
        )

    def _update_override(self, override_id, **changes):
        for key, row in self._overrides.items():
            if row.override_id == override_id:
                self._overrides[key] = replace(row, **changes)
                return

    def pending_overrides(self, limit):
        pending = [o for o in self._overrides.values() if o.sync_status == "pending"]
        return pending[:limit]

    def mark_override_synced(self, override_id, assessment_id):
        self._update_override(
            override_id, sync_status="synced", mlflow_assessment_id=assessment_id,
            last_sync_error=None,
        )

    def mark_override_failed(self, override_id, error):
        row = next(o for o in self._overrides.values() if o.override_id == override_id)
        attempts = row.sync_attempts + 1
        self._update_override(
            override_id,
            sync_attempts=attempts,
            last_sync_error=error,
            sync_status="failed" if attempts >= MAX_SYNC_ATTEMPTS else "pending",
        )

    def mark_override_no_trace(self, override_id):
        self._update_override(override_id, sync_status="no_trace")

    def count_pending_overrides(self):
        return sum(1 for o in self._overrides.values() if o.sync_status == "pending")