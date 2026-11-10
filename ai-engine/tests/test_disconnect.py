"""Work is cancelled when the client hangs up, so the engine stops using the GPU for nobody."""

import asyncio

import pytest

from api.disconnect import ClientDisconnected, run_unless_disconnected


class Request:
    """A request that reports itself disconnected after `after` polls (None = never)."""

    def __init__(self, after: int | None = None) -> None:
        self.after, self.polls = after, 0

    async def is_disconnected(self) -> bool:
        self.polls += 1
        return self.after is not None and self.polls >= self.after


def test_finished_work_is_returned() -> None:
    async def work() -> str:
        await asyncio.sleep(0.02)
        return "assessment"

    assert asyncio.run(run_unless_disconnected(Request(), work(), poll_seconds=0.01)) == "assessment"


def test_work_that_raises_propagates_its_error() -> None:
    async def work() -> None:
        raise ValueError("model gone")

    with pytest.raises(ValueError, match="model gone"):
        asyncio.run(run_unless_disconnected(Request(), work(), poll_seconds=0.01))


def test_a_disconnected_client_cancels_the_work() -> None:
    state = {"cancelled": False, "finished": False}

    async def work() -> None:
        try:
            await asyncio.sleep(30)  # stands in for a long Ollama generation
            state["finished"] = True
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def scenario() -> float:
        begun = asyncio.get_running_loop().time()
        with pytest.raises(ClientDisconnected):
            await run_unless_disconnected(Request(after=2), work(), poll_seconds=0.02)
        return asyncio.get_running_loop().time() - begun

    elapsed = asyncio.run(scenario())

    assert state == {"cancelled": True, "finished": False}
    assert elapsed < 2  # stopped promptly, not after the 30 s of work


def test_cleanup_in_the_cancelled_work_still_runs() -> None:
    # e.g. the model-slot arbiter release and the MLflow run being marked FAILED
    state = {"cleaned": False}

    async def work() -> None:
        try:
            await asyncio.sleep(30)
        finally:
            state["cleaned"] = True

    with pytest.raises(ClientDisconnected):
        asyncio.run(run_unless_disconnected(Request(after=1), work(), poll_seconds=0.01))

    assert state["cleaned"] is True


def test_cancelling_the_handler_cancels_the_work_too() -> None:
    state = {"cancelled": False}

    async def work() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def scenario() -> None:
        handler = asyncio.ensure_future(run_unless_disconnected(Request(), work(), poll_seconds=0.01))
        await asyncio.sleep(0.05)
        handler.cancel()
        with pytest.raises(asyncio.CancelledError):
            await handler
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert state["cancelled"] is True
