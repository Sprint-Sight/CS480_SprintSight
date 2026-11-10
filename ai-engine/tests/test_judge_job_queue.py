"""The judge queue is durable: a job is a row that survives restarts and crashes."""

import pytest

from judges.job_queue import DEAD, DONE, QUEUED, RUNNING, JudgeJobQueue


class Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def make_queue(tmp_path, clock, **kwargs) -> JudgeJobQueue:
    return JudgeJobQueue(tmp_path / "jobs.sqlite3", clock=clock, **kwargs)


def enqueue(queue: JudgeJobQueue, trace_id: str = "tr-1", **overrides) -> bool:
    fields = {
        "trace_id": trace_id,
        "experiment_name": "exp",
        "team_id": "team-a",
        "sprint_id": "s1",
        "prompt_versions": {"Evaluate_testing": 3},
    }
    return queue.enqueue(**{**fields, **overrides})


def test_a_job_survives_the_process_that_queued_it(tmp_path, clock) -> None:
    enqueue(make_queue(tmp_path, clock))

    restarted = make_queue(tmp_path, clock)  # a new object on the same file = a restart
    job = restarted.claim_next()

    assert job is not None
    assert (job.trace_id, job.team_id, job.sprint_id) == ("tr-1", "team-a", "s1")
    assert job.prompt_versions == {"Evaluate_testing": 3}
    assert job.attempts == 1


def test_enqueueing_the_same_trace_twice_is_idempotent(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock)
    assert enqueue(queue) is True
    assert enqueue(queue) is False
    assert queue.stats()[QUEUED] == 1


def test_jobs_are_claimed_oldest_first_and_only_once(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock)
    enqueue(queue, "tr-1")
    enqueue(queue, "tr-2")

    first, second, third = queue.claim_next(), queue.claim_next(), queue.claim_next()

    assert (first.trace_id, second.trace_id, third) == ("tr-1", "tr-2", None)


def test_completed_jobs_are_not_run_again(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock)
    enqueue(queue)
    queue.complete(queue.claim_next().job_id)

    assert queue.claim_next() is None
    assert queue.stats()[DONE] == 1


def test_a_failed_job_waits_out_its_retry_delay(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock)
    enqueue(queue)
    job = queue.claim_next()

    assert queue.fail(job.job_id, "timeout: slow", retry_delay=300) == QUEUED
    assert queue.claim_next() is None  # not due yet
    assert queue.pending_count() == 0

    clock.now += 301
    retry = queue.claim_next()
    assert retry is not None and retry.attempts == 2


def test_a_job_that_keeps_failing_ends_up_dead_not_retried_forever(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock, max_attempts=2)
    enqueue(queue)

    first = queue.claim_next()
    assert queue.fail(first.job_id, "boom", retry_delay=0) == QUEUED
    second = queue.claim_next()
    assert queue.fail(second.job_id, "boom again", retry_delay=0) == DEAD

    assert queue.claim_next() is None
    assert queue.stats()[DEAD] == 1


def test_a_job_whose_worker_died_is_taken_over_after_the_lease_expires(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock, lease_seconds=60)
    enqueue(queue)
    assert queue.claim_next() is not None  # claimed, then the worker "dies"

    assert queue.claim_next() is None  # lease still valid
    clock.now += 61
    taken_over = queue.claim_next()

    assert taken_over is not None and taken_over.attempts == 2


def test_a_job_that_crashes_every_worker_is_marked_dead(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock, lease_seconds=10, max_attempts=2)
    enqueue(queue)
    for _ in range(2):
        assert queue.claim_next() is not None
        clock.now += 11  # worker dies without reporting back

    assert queue.claim_next() is None
    assert queue.stats()[DEAD] == 1


def test_startup_gives_orphaned_running_jobs_back(tmp_path, clock) -> None:
    queue = make_queue(tmp_path, clock)
    enqueue(queue)
    queue.claim_next()
    assert queue.stats()[RUNNING] == 1

    assert make_queue(tmp_path, clock).requeue_running() == 1
    assert queue.stats()[QUEUED] == 1
    assert queue.claim_next().attempts == 2  # the crashed attempt still counts
