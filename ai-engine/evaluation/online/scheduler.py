"""Runs judge jobs away from grading requests.

The judge model (phi) and the grading model (qwen, gemma, ...) share one Ollama server that
holds a single model at a time (OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=1 on the
GPU job). If a judge call and a grading call overlap, each evicts the other's model: both
pay a cold load, and the slow one can hit its timeout, which then shows up as a "failed
dimension" or a failed judge that has nothing to do with answer quality.

`ModelSlotArbiter` serialises them with grading as the priority:
  * a judge job starts only when no grading request is running or waiting, and grading has
    been quiet for `judge_quiet_seconds`;
  * a grading request that arrives while a judge job runs waits for it, but only up to
    `grader_max_wait_seconds`, so a stuck judge can never block grading indefinitely.

`JudgeWorker` drains the durable queue (evaluation/online/job_queue.py) through the arbiter.

The arbiter lives in one process. It coordinates the request handlers and the worker thread
of a single engine; it does not coordinate separate engine replicas.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager

from services.failures import classify_failure, failure_detail

from evaluation.online.job_queue import JudgeJob, JudgeJobQueue

log = logging.getLogger("sprintsight.judges.scheduler")

GRADER_MAX_WAIT_SECONDS = float(os.getenv("GRADER_MAX_WAIT_FOR_JUDGE_SECONDS", "900"))
JUDGE_QUIET_SECONDS = float(os.getenv("JUDGE_IDLE_QUIET_SECONDS", "2"))
JUDGE_POLL_SECONDS = float(os.getenv("JUDGE_WORKER_POLL_SECONDS", "2"))
JUDGE_SLOT_WAIT_SECONDS = float(os.getenv("JUDGE_SLOT_WAIT_SECONDS", "30"))
JUDGE_RETRY_DELAY_SECONDS = float(os.getenv("JUDGE_RETRY_DELAY_SECONDS", "300"))
_GRADER_POLL_SECONDS = 0.25


class ModelSlotArbiter:
    def __init__(
        self,
        *,
        grader_max_wait_seconds: float = GRADER_MAX_WAIT_SECONDS,
        judge_quiet_seconds: float = JUDGE_QUIET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.grader_max_wait_seconds = grader_max_wait_seconds
        self.judge_quiet_seconds = judge_quiet_seconds
        self._clock = clock
        self._cv = threading.Condition()
        self._graders_active = 0
        self._graders_waiting = 0
        self._judge_active = False
        self._last_grading_end = -math.inf

    @property
    def judge_active(self) -> bool:
        with self._cv:
            return self._judge_active

    @asynccontextmanager
    async def grading(self) -> AsyncIterator[None]:
        """Hold the model slot for one grading request (async: called from the route)."""
        deadline = self._clock() + self.grader_max_wait_seconds
        with self._cv:
            self._graders_waiting += 1  # visible immediately, so the judge worker backs off
        acquired = False
        try:
            while True:
                with self._cv:
                    judge_running = self._judge_active
                    if not judge_running or self._clock() >= deadline:
                        if judge_running:
                            log.warning(
                                "Grading proceeds after waiting %.0fs for a judge job; "
                                "expect a model reload.", self.grader_max_wait_seconds,
                            )
                        self._graders_waiting -= 1
                        self._graders_active += 1
                        acquired = True
                        break
                await asyncio.sleep(_GRADER_POLL_SECONDS)
            yield
        finally:
            with self._cv:
                if acquired:
                    self._graders_active -= 1
                    self._last_grading_end = self._clock()
                else:  # cancelled or failed while still waiting
                    self._graders_waiting -= 1
                self._cv.notify_all()

    @contextmanager
    def judging(self, timeout: float | None = None) -> Iterator[None]:
        """Hold the model slot for one judge job (sync: called from the worker thread).
        Raises TimeoutError if grading keeps the slot busy for longer than `timeout`."""
        deadline = None if timeout is None else self._clock() + timeout
        with self._cv:
            while True:
                idle = self._graders_active == 0 and self._graders_waiting == 0 and not self._judge_active
                quiet = self._clock() - self._last_grading_end >= self.judge_quiet_seconds
                if idle and quiet:
                    self._judge_active = True
                    break
                remaining = None if deadline is None else deadline - self._clock()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("model slot busy with grading")
                self._cv.wait(0.25 if remaining is None else min(0.25, remaining))
        try:
            yield
        finally:
            with self._cv:
                self._judge_active = False
                self._cv.notify_all()


class JudgeWorker:
    def __init__(
        self,
        queue: JudgeJobQueue,
        runner: Callable[[JudgeJob], None],
        arbiter: ModelSlotArbiter,
        *,
        poll_seconds: float = JUDGE_POLL_SECONDS,
        slot_wait_seconds: float = JUDGE_SLOT_WAIT_SECONDS,
        retry_delay_seconds: float = JUDGE_RETRY_DELAY_SECONDS,
    ) -> None:
        self.queue = queue
        self.runner = runner
        self.arbiter = arbiter
        self.poll_seconds = poll_seconds
        self.slot_wait_seconds = slot_wait_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Process at most one job. Returns True if a job was run (successfully or not)."""
        if self.queue.pending_count() == 0:
            return False
        try:
            with self.arbiter.judging(timeout=self.slot_wait_seconds):
                job = self.queue.claim_next()
                if job is None:
                    return False
                self._execute(job)
                return True
        except TimeoutError:
            return False  # grading is busy; no attempt was consumed, try again shortly

    def _execute(self, job: JudgeJob) -> None:
        try:
            self.runner(job)
        except Exception as exc:
            failure_class = classify_failure(exc)
            status = self.queue.fail(
                job.job_id,
                f"{failure_class.value}: {failure_detail(exc)}",
                retry_delay=self.retry_delay_seconds,
            )
            log.exception(
                "Judge job for trace %s failed (attempt %d, %s); status now '%s'.",
                job.trace_id, job.attempts, failure_class.value, status,
            )
        else:
            self.queue.complete(job.job_id)
            log.info("Judge job for trace %s completed (attempt %d).", job.trace_id, job.attempts)

    def _loop(self) -> None:
        recovered = self.queue.requeue_running()
        if recovered:
            log.warning("Re-queued %d judge job(s) that were running when the process stopped.", recovered)
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                log.exception("Judge worker loop error; continuing.")
                worked = False
            if not worked:
                self._stop.wait(self.poll_seconds)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="judge-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)


def run_judge_job(job: JudgeJob) -> None:
    """The production runner: judge the trace, then evaluate prompt promotion."""
    from mlflow import MlflowClient

    from evaluation.online.promote import (
        run_judge_and_promotion,  # lazy: pulls in mlflow.genai and the scorers
    )

    run_judge_and_promotion(
        job.experiment_name, job.trace_id, job.team_id, job.prompt_versions,
        MlflowClient(), job.sprint_id,
    )


# ---- process-wide instances -------------------------------------------------------------

_instances_lock = threading.Lock()
_queue: JudgeJobQueue | None = None
_arbiter: ModelSlotArbiter | None = None
_worker: JudgeWorker | None = None


def get_judge_queue() -> JudgeJobQueue:
    global _queue
    with _instances_lock:
        if _queue is None:
            _queue = JudgeJobQueue(os.getenv("JUDGE_QUEUE_DB") or None)
        return _queue


def get_arbiter() -> ModelSlotArbiter:
    global _arbiter
    with _instances_lock:
        if _arbiter is None:
            _arbiter = ModelSlotArbiter()
        return _arbiter


def start_judge_worker() -> JudgeWorker | None:
    """Start the background worker unless JUDGE_WORKER_ENABLED=0 (e.g. a one-off script)."""
    global _worker
    if os.getenv("JUDGE_WORKER_ENABLED", "1").strip().lower() in {"0", "false", "no"}:
        log.info("Judge worker disabled by JUDGE_WORKER_ENABLED.")
        return None
    worker = JudgeWorker(get_judge_queue(), run_judge_job, get_arbiter())
    worker.start()
    _worker = worker
    return worker


def stop_judge_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
