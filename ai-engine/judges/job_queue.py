"""A small durable queue for judge jobs, backed by SQLite.

FastAPI's `BackgroundTasks` live in memory: a restart between "assessment returned" and
"judge finished" silently drops the job, so that trace is never judged and never flagged.
Here a job is a row. It survives a restart, a job whose worker died is picked up again,
and a job that keeps failing ends up `dead` (visible, not retried forever) instead of
vanishing.

SQLite keeps this dependency-free and testable. The file must live on storage that outlives
the process (the compose file bind-mounts the project directory; override with
JUDGE_QUEUE_DB). It is single-node by design: one engine process owns the file. Running
several engine replicas would call for a shared queue (Postgres or Redis) behind this same
interface.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("sprintsight.judges.queue")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "judge_jobs.sqlite3"
MAX_ATTEMPTS = int(os.getenv("JUDGE_JOB_MAX_ATTEMPTS", "3"))
# A running job whose lease expired is presumed orphaned (its worker died). Longer than the
# slowest judge run, short enough to recover within the hour.
LEASE_SECONDS = float(os.getenv("JUDGE_JOB_LEASE_SECONDS", "3600"))

QUEUED, RUNNING, DONE, DEAD = "queued", "running", "done", "dead"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS judge_jobs (
    job_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id        TEXT NOT NULL UNIQUE,
    experiment_name TEXT NOT NULL,
    team_id         TEXT NOT NULL,
    sprint_id       TEXT,
    prompt_versions TEXT NOT NULL,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    run_after       REAL NOT NULL,
    lease_until     REAL,
    last_error      TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
)
"""


@dataclass(frozen=True)
class JudgeJob:
    job_id: int
    trace_id: str
    experiment_name: str
    team_id: str
    sprint_id: str | None
    prompt_versions: dict
    attempts: int


class JudgeJobQueue:
    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        lease_seconds: float = LEASE_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path) if path else DEFAULT_DB_PATH
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self._clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # One short-lived connection per operation: safe across the request threads and the
        # worker thread, and `isolation_level=None` lets us issue BEGIN IMMEDIATE ourselves.
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    def enqueue(
        self,
        *,
        trace_id: str,
        experiment_name: str,
        team_id: str,
        sprint_id: str | None,
        prompt_versions: dict,
    ) -> bool:
        """Add a job. Returns False when this trace is already queued (idempotent)."""
        now = self._clock()
        with closing(self._connect()) as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO judge_jobs
                   (trace_id, experiment_name, team_id, sprint_id, prompt_versions,
                    status, attempts, run_after, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                (trace_id, experiment_name, team_id, sprint_id,
                 json.dumps(prompt_versions), QUEUED, now, now, now),
            )
            return cursor.rowcount == 1

    def pending_count(self) -> int:
        """Jobs that are waiting to run (queued and due, or running with an expired lease)."""
        now = self._clock()
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT COUNT(*) FROM judge_jobs
                   WHERE (status = ? AND run_after <= ?) OR (status = ? AND lease_until < ?)""",
                (QUEUED, now, RUNNING, now),
            ).fetchone()
        return int(row[0])

    def claim_next(self) -> JudgeJob | None:
        """Take the oldest due job and lease it. A job whose lease expired is taken over, but
        only until it has used up its attempts: a job that crashes its worker every time is
        marked dead instead of crash-looping."""
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                while True:
                    row = db.execute(
                        """SELECT * FROM judge_jobs
                           WHERE (status = ? AND run_after <= ?) OR (status = ? AND lease_until < ?)
                           ORDER BY job_id LIMIT 1""",
                        (QUEUED, now, RUNNING, now),
                    ).fetchone()
                    if row is None:
                        db.execute("COMMIT")
                        return None
                    if row["attempts"] >= self.max_attempts:
                        db.execute(
                            "UPDATE judge_jobs SET status = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
                            (DEAD, row["last_error"] or "attempts exhausted (worker lost)", now, row["job_id"]),
                        )
                        log.error("Judge job for trace %s is dead after %d attempts.", row["trace_id"], row["attempts"])
                        continue
                    db.execute(
                        """UPDATE judge_jobs SET status = ?, attempts = attempts + 1,
                           lease_until = ?, updated_at = ? WHERE job_id = ?""",
                        (RUNNING, now + self.lease_seconds, now, row["job_id"]),
                    )
                    db.execute("COMMIT")
                    return JudgeJob(
                        job_id=row["job_id"],
                        trace_id=row["trace_id"],
                        experiment_name=row["experiment_name"],
                        team_id=row["team_id"],
                        sprint_id=row["sprint_id"],
                        prompt_versions=json.loads(row["prompt_versions"]),
                        attempts=row["attempts"] + 1,
                    )
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def complete(self, job_id: int) -> None:
        with closing(self._connect()) as db:
            db.execute(
                "UPDATE judge_jobs SET status = ?, lease_until = NULL, updated_at = ? WHERE job_id = ?",
                (DONE, self._clock(), job_id),
            )

    def fail(self, job_id: int, error: str, *, retry_delay: float = 300.0) -> str:
        """Record a failed attempt. Returns the new status: `queued` (will retry after
        `retry_delay`) or `dead` (attempts exhausted)."""
        now = self._clock()
        with closing(self._connect()) as db:
            row = db.execute("SELECT attempts FROM judge_jobs WHERE job_id = ?", (job_id,)).fetchone()
            exhausted = row is not None and row["attempts"] >= self.max_attempts
            status = DEAD if exhausted else QUEUED
            db.execute(
                """UPDATE judge_jobs SET status = ?, last_error = ?, lease_until = NULL,
                   run_after = ?, updated_at = ? WHERE job_id = ?""",
                (status, error, now + retry_delay, now, job_id),
            )
        return status

    def requeue_running(self) -> int:
        """At process start nothing can legitimately still be running: give orphaned jobs back."""
        with closing(self._connect()) as db:
            cursor = db.execute(
                "UPDATE judge_jobs SET status = ?, lease_until = NULL, updated_at = ? WHERE status = ?",
                (QUEUED, self._clock(), RUNNING),
            )
            return cursor.rowcount

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT status, COUNT(*) AS n FROM judge_jobs GROUP BY status").fetchall()
        counts = dict.fromkeys((QUEUED, RUNNING, DONE, DEAD), 0)
        counts.update({row["status"]: row["n"] for row in rows})
        return counts
