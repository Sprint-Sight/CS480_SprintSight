"""The Postgres job store, against a real database (skipped when TEST_DATABASE_URL is not set).

Every other test uses the in-memory repositories, so nothing else runs this SQL: the atomic
terminal write, the heartbeat and the stale-job cleanup (M4)."""

import psycopg.errors
import pytest

from app.repositories.postgres import (
    PostgresAssessmentJobRepository,
    ensure_assessment_job_schema,
)
from app.schemas.assessment import AssessRequest
from app.services.assessmentService.heartbeat import STOPPED_BACKEND_MESSAGE, JobHeartbeat

STALE = 120.0


@pytest.fixture
def pool(postgres_pool):
    with postgres_pool.connection() as connection:
        connection.execute("TRUNCATE assessment_jobs CASCADE")
    return postgres_pool


def repo(pool, owner: str = "worker-a") -> PostgresAssessmentJobRepository:
    return PostgresAssessmentJobRepository(pool, owner_id=owner)


def request_for() -> AssessRequest:
    return AssessRequest(course_id="c1", project_id="p1", sprint_id="sp1", model_name="m")


def run_sql(pool, sql: str, *params) -> None:
    with pool.connection() as connection:
        connection.execute(sql, params)


def age_heartbeat(pool, job_id: str, seconds: float | None) -> None:
    """Make a job's last sign of life `seconds` old, or never (None)."""
    if seconds is None:
        run_sql(pool, "UPDATE assessment_jobs SET heartbeat_at = NULL WHERE job_id = %s", job_id)
    else:
        run_sql(
            pool,
            "UPDATE assessment_jobs SET heartbeat_at = now() - make_interval(secs => %s) "
            "WHERE job_id = %s",
            seconds,
            job_id,
        )


def test_a_job_is_created_with_one_started_event_and_its_owner(pool) -> None:
    jobs = repo(pool)

    job = jobs.create_job(request_for())

    assert (job.status, job.progress, job.model_name) == ("queued", 0, "m")
    assert [e.event for e in jobs.list_events(job.job_id)] == ["started"]
    with pool.connection() as connection:
        row = connection.execute(
            "SELECT owner_id, heartbeat_at FROM assessment_jobs WHERE job_id = %s", (job.job_id,)
        ).fetchone()
    assert row["owner_id"] == "worker-a" and row["heartbeat_at"] is not None


def test_update_job_changes_only_the_fields_it_is_given(pool) -> None:
    jobs = repo(pool)
    job = jobs.create_job(request_for())

    jobs.update_job(job.job_id, status="collecting_data", progress=30)
    updated = jobs.update_job(job.job_id, report_id="rpt-1")

    assert updated is not None
    assert (updated.status, updated.progress, updated.report_id) == ("collecting_data", 30, "rpt-1")


def test_finish_job_writes_the_terminal_event_and_status_together(pool) -> None:
    jobs = repo(pool)
    job = jobs.create_job(request_for())

    finished = jobs.finish_job(
        job.job_id, "completed", {"status": "completed"}, status="completed", report_id="rpt-9"
    )

    assert finished is not None
    assert (finished.status, finished.progress, finished.report_id) == ("completed", 100, "rpt-9")
    assert [e.event for e in jobs.list_events(job.job_id)] == ["started", "completed"]


def test_finish_job_leaves_no_event_behind_when_the_status_write_fails(pool) -> None:
    """The terminal event and status commit together: a failure must not leave half of them."""
    jobs = repo(pool)
    job = jobs.create_job(request_for())

    with pytest.raises(psycopg.errors.NotNullViolation):
        jobs.finish_job(job.job_id, "completed", {}, status=None)  # type: ignore[arg-type]

    assert [e.event for e in jobs.list_events(job.job_id)] == ["started"]
    state = jobs.get_job(job.job_id)
    assert state is not None and state.status == "queued"


def test_finish_job_for_an_unknown_job_does_nothing(pool) -> None:
    jobs = repo(pool)

    assert jobs.finish_job("job-missing", "failed", {}, status="failed") is None
    assert jobs.list_events("job-missing") == []


def test_a_restart_only_fails_the_jobs_of_a_backend_that_stopped(pool) -> None:
    other = repo(pool, "worker-gone")
    me = repo(pool, "worker-new")
    alive_elsewhere = repo(pool, "worker-alive").create_job(request_for())
    abandoned = other.create_job(request_for())
    never_heartbeat = other.create_job(request_for())  # a row from before heartbeats existed
    already_done = other.create_job(request_for())
    other.finish_job(already_done.job_id, "completed", {}, status="completed")
    age_heartbeat(pool, abandoned.job_id, 600)
    age_heartbeat(pool, never_heartbeat.job_id, None)
    age_heartbeat(pool, already_done.job_id, 600)
    age_heartbeat(pool, alive_elsewhere.job_id, 5)

    failed = me.fail_stale_jobs(STALE, "stopped")

    assert failed == 2

    def status_of(job) -> str:
        state = me.get_job(job.job_id)
        assert state is not None
        return state.status

    assert status_of(alive_elsewhere) == "queued"  # another live worker keeps its job
    assert status_of(abandoned) == status_of(never_heartbeat) == "failed"
    assert status_of(already_done) == "completed"
    last = me.list_events(abandoned.job_id)[-1]
    assert last.event == "failed"
    assert last.data["transient"] is True and last.data["error_kind"] == "interrupted"
    assert last.data["error_message"] == "stopped"


def test_starting_a_second_worker_does_not_fail_the_first_workers_running_job(pool) -> None:
    first = repo(pool, "worker-1")
    running = first.create_job(request_for())
    first.update_job(running.job_id, status="ai_evaluating", progress=50)

    second = repo(pool, "worker-2")
    assert second.fail_stale_jobs(STALE, "stopped") == 0

    state = first.get_job(running.job_id)
    assert state is not None and state.status == "ai_evaluating"


def test_a_process_never_fails_its_own_jobs_even_if_its_heartbeat_looks_old(pool) -> None:
    me = repo(pool)
    job = me.create_job(request_for())
    age_heartbeat(pool, job.job_id, 600)

    assert me.fail_stale_jobs(STALE, "stopped") == 0
    assert me.touch_owned_jobs() == 1  # and one heartbeat makes it fresh again


def test_the_heartbeat_keeps_a_long_job_alive_and_leaves_finished_ones_alone(pool) -> None:
    me, other = repo(pool, "worker-a"), repo(pool, "worker-b")
    long_running = me.create_job(request_for())
    finished = me.create_job(request_for())
    me.finish_job(finished.job_id, "completed", {}, status="completed")
    for job in (long_running, finished):
        age_heartbeat(pool, job.job_id, 600)

    assert me.touch_owned_jobs() == 1  # only the unfinished one

    assert other.fail_stale_jobs(STALE, "stopped") == 0
    state = me.get_job(long_running.job_id)
    assert state is not None and state.status == "queued"


def test_one_heartbeat_pass_touches_its_jobs_and_fails_the_abandoned(pool) -> None:
    me, gone = repo(pool, "worker-a"), repo(pool, "worker-gone")
    mine, abandoned = me.create_job(request_for()), gone.create_job(request_for())
    age_heartbeat(pool, mine.job_id, 100)
    age_heartbeat(pool, abandoned.job_id, 600)

    JobHeartbeat(me, interval_seconds=30, stale_after_seconds=STALE).beat()

    abandoned_state, mine_state = me.get_job(abandoned.job_id), me.get_job(mine.job_id)
    assert abandoned_state is not None and abandoned_state.status == "failed"
    assert me.list_events(abandoned.job_id)[-1].data["error_message"] == STOPPED_BACKEND_MESSAGE
    assert mine_state is not None and mine_state.status == "queued"


def test_old_finished_jobs_are_pruned_and_running_ones_kept(pool) -> None:
    jobs = repo(pool)
    old_done, old_running = jobs.create_job(request_for()), jobs.create_job(request_for())
    jobs.finish_job(old_done.job_id, "completed", {}, status="completed")
    run_sql(pool, "UPDATE assessment_jobs SET updated_at = now() - interval '60 days'")

    assert jobs.prune(older_than_days=30) == 1
    assert jobs.get_job(old_done.job_id) is None
    assert jobs.get_job(old_running.job_id) is not None


def test_an_existing_jobs_table_gains_the_heartbeat_columns(pool) -> None:
    run_sql(pool, "ALTER TABLE assessment_jobs DROP COLUMN owner_id, DROP COLUMN heartbeat_at")

    ensure_assessment_job_schema(pool)
    ensure_assessment_job_schema(pool)  # and it can run again

    job = repo(pool).create_job(request_for())
    assert job.job_id
