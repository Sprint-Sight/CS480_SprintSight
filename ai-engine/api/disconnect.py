"""Stop work nobody is waiting for.

FastAPI does not cancel a route handler when its client hangs up. The backend gives up on an
assessment after AI_ENGINE_TIMEOUT_SECONDS and marks the job failed, but the engine would go
on grading: Ollama kept generating for several more minutes, holding the GPU and the model slot
for a result that is then thrown away.

`run_unless_disconnected` runs the work as a task and polls the connection. When the client has
gone it cancels the task. The cancellation reaches the in-flight HTTP request to Ollama, which
closes the connection, and Ollama stops generating.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable
from typing import Protocol, TypeVar

log = logging.getLogger("sprintsight.api.disconnect")

T = TypeVar("T")
DEFAULT_POLL_SECONDS = 2.0


class _HasIsDisconnected(Protocol):
    async def is_disconnected(self) -> bool: ...


class ClientDisconnected(Exception):
    """The caller closed the connection before the work finished; the work was cancelled."""


async def run_unless_disconnected(
    request: _HasIsDisconnected,
    work: Awaitable[T],
    *,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> T:
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll_seconds)
            if done:
                return task.result()
            if await request.is_disconnected():
                log.warning("Client disconnected before the work finished; cancelling it.")
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                raise ClientDisconnected
    except asyncio.CancelledError:
        # The server itself is shutting down, or this handler was cancelled: don't leave the work running.
        task.cancel()
        raise
