"""Grading has priority for the single Ollama model slot; judging yields to it."""

import asyncio
import threading
import time

import pytest

from evaluation.online.job_queue import DEAD, DONE, QUEUED, JudgeJobQueue
from evaluation.online.scheduler import JudgeWorker, ModelSlotArbiter


def arbiter(**kwargs) -> ModelSlotArbiter:
    return ModelSlotArbiter(**{"judge_quiet_seconds": 0.0, "grader_max_wait_seconds": 5.0, **kwargs})


def test_judging_is_refused_while_a_grading_request_holds_the_slot() -> None:
    slot = arbiter()

    async def scenario() -> None:
        async with slot.grading():
            with pytest.raises(TimeoutError), slot.judging(timeout=0.05):
                pytest.fail("a judge job must not start during grading")

    asyncio.run(scenario())


def test_judging_waits_for_a_grading_request_that_is_still_queued_up() -> None:
    slot = arbiter()
    judged = threading.Event()

    async def scenario() -> None:
        async with slot.grading():
            def judge() -> None:
                with slot.judging(timeout=2):
                    judged.set()

            thread = threading.Thread(target=judge)
            thread.start()
            await asyncio.sleep(0.3)
            assert not judged.is_set()  # still blocked by the active grader
        thread.join(2)

    asyncio.run(scenario())
    assert judged.is_set()  # ...and ran once grading released the slot


def test_grading_waits_for_a_running_judge_job() -> None:
    slot = arbiter()
    release_judge = threading.Event()
    judge_started = threading.Event()
    order: list[str] = []

    def judge() -> None:
        with slot.judging(timeout=2):
            judge_started.set()
            release_judge.wait(2)
            order.append("judge done")

    thread = threading.Thread(target=judge)
    thread.start()
    assert judge_started.wait(2)

    async def scenario() -> None:
        threading.Timer(0.3, release_judge.set).start()
        async with slot.grading():
            order.append("grading started")

    asyncio.run(scenario())
    thread.join(2)
    assert order == ["judge done", "grading started"]


def test_grading_is_never_blocked_forever_by_a_stuck_judge() -> None:
    slot = arbiter(grader_max_wait_seconds=0.3)
    stuck = threading.Event()
    started = threading.Event()

    def judge() -> None:
        with slot.judging(timeout=2):
            started.set()
            stuck.wait(5)

    thread = threading.Thread(target=judge)
    thread.start()
    assert started.wait(2)

    async def scenario() -> float:
        begun = time.monotonic()
        async with slot.grading():
            return time.monotonic() - begun

    waited = asyncio.run(scenario())
    stuck.set()
    thread.join(2)
    assert 0.25 <= waited < 2


def test_judging_waits_for_grading_to_go_quiet() -> None:
    slot = arbiter(judge_quiet_seconds=0.4)

    async def scenario() -> None:
        async with slot.grading():
            pass
        with pytest.raises(TimeoutError), slot.judging(timeout=0.05):
            pytest.fail("grading just finished; the judge should still be holding off")
        await asyncio.sleep(0.45)
        with slot.judging(timeout=0.5):
            pass

    asyncio.run(scenario())


def test_a_cancelled_grading_request_does_not_leave_the_judge_blocked() -> None:
    slot = arbiter()
    holder = threading.Event()
    judge_started = threading.Event()

    def judge() -> None:
        with slot.judging(timeout=2):
            judge_started.set()
            holder.wait(2)

    thread = threading.Thread(target=judge)
    thread.start()
    assert judge_started.wait(2)

    async def scenario() -> None:
        async def request() -> None:
            async with slot.grading():
                pytest.fail("should have been cancelled while waiting")

        task = asyncio.create_task(request())
        await asyncio.sleep(0.3)  # waiting behind the judge
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    holder.set()
    thread.join(2)
    with slot.judging(timeout=0.5):  # not wedged by the abandoned waiter
        pass


# ------------------------------------------------------------------------ the worker


def make_worker(tmp_path, runner, slot=None, **kwargs) -> tuple[JudgeWorker, JudgeJobQueue]:
    queue = JudgeJobQueue(tmp_path / "jobs.sqlite3", max_attempts=2)
    queue.enqueue(trace_id="tr-1", experiment_name="e", team_id="t", sprint_id="s", prompt_versions={})
    worker = JudgeWorker(queue, runner, slot or arbiter(), retry_delay_seconds=0, slot_wait_seconds=0.05, **kwargs)
    return worker, queue


def test_worker_runs_a_job_and_marks_it_done(tmp_path) -> None:
    seen = []
    worker, queue = make_worker(tmp_path, lambda job: seen.append(job.trace_id))

    assert worker.run_once() is True

    assert seen == ["tr-1"]
    assert queue.stats()[DONE] == 1
    assert worker.run_once() is False  # nothing left


def test_worker_requeues_a_failing_job_then_gives_up(tmp_path) -> None:
    def boom(job) -> None:
        raise ConnectionError("ollama down")

    worker, queue = make_worker(tmp_path, boom)

    assert worker.run_once() is True
    assert queue.stats()[QUEUED] == 1  # failed once, will retry
    assert worker.run_once() is True
    assert queue.stats()[DEAD] == 1  # attempts exhausted
    assert worker.run_once() is False


def test_worker_does_not_spend_an_attempt_while_grading_has_the_slot(tmp_path) -> None:
    ran = []
    slot = arbiter()
    worker, queue = make_worker(tmp_path, lambda job: ran.append(job), slot=slot)

    async def scenario() -> bool:
        async with slot.grading():
            return worker.run_once()

    assert asyncio.run(scenario()) is False
    assert ran == []
    job = queue.claim_next()
    assert job is not None and job.attempts == 1  # the blocked poll cost nothing


def test_worker_loop_recovers_jobs_orphaned_by_a_crash_and_stops_cleanly(tmp_path) -> None:
    seen = threading.Event()
    queue = JudgeJobQueue(tmp_path / "jobs.sqlite3")
    queue.enqueue(trace_id="tr-9", experiment_name="e", team_id="t", sprint_id="s", prompt_versions={})
    queue.claim_next()  # a previous process claimed it and died

    worker = JudgeWorker(queue, lambda job: seen.set(), arbiter(), poll_seconds=0.05, slot_wait_seconds=0.05)
    worker.start()
    try:
        assert seen.wait(3), "the orphaned job was never picked up"
    finally:
        worker.stop(2)
    assert queue.stats()[DONE] == 1
