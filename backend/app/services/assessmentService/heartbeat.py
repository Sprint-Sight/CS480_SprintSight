"""Keeps this backend's assessment jobs marked alive, and fails the jobs of backends that stopped.

A job is a database row, so it outlives the process that runs it. Without a heartbeat the only
safe thing to do at startup was to fail every unfinished job, which is wrong as soon as two
workers share a database: starting the second would fail the first one's running jobs.
"""

import logging
import threading
from typing import Protocol

logger = logging.getLogger(__name__)

STOPPED_BACKEND_MESSAGE = "The backend running this assessment stopped before it finished."


class _JobStore(Protocol):
    def touch_owned_jobs(self) -> int: ...

    def fail_stale_jobs(self, stale_after_seconds: float, message: str) -> int: ...


class JobHeartbeat:
    def __init__(
        self, jobs: _JobStore, interval_seconds: float, stale_after_seconds: float
    ) -> None:
        self._jobs = jobs
        self._interval = max(0.5, interval_seconds)
        # Never fail a job before it has had a few chances to heartbeat.
        self._stale_after = max(stale_after_seconds, 3 * self._interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def beat(self) -> None:
        """One pass: say this process is alive, then fail what a dead process left behind."""
        self._jobs.touch_owned_jobs()
        failed = self._jobs.fail_stale_jobs(self._stale_after, STOPPED_BACKEND_MESSAGE)
        if failed:
            logger.warning("Marked %d abandoned assessment job(s) as failed.", failed)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="job-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.beat()
            except Exception:  # a database blip must not end the heartbeat
                logger.exception("The assessment job heartbeat failed.")
