"""eval.progress is written as 'done/total' on the run: 0/N at start, +1 per finished step."""

import asyncio

from services import evaluator as ev


class FakeRun:
    def __init__(self, fail: bool = False):
        self.tags: list[tuple[str, str]] = []
        self.fail = fail

    def set_tag(self, key, value):
        if self.fail:
            raise RuntimeError("mlflow down")
        self.tags.append((key, value))

def test_reporter_starts_at_zero_and_counts_each_step():
    run = FakeRun()
    report = ev.make_progress_reporter(run, total_steps=3)

    report(initial=True)
    report()
    report()
    report()

    # 0 first: it also clears a stale value if the run is ever reused.
    assert [v for _, v in run.tags] == ["0/3", "1/3", "2/3", "3/3"]
    assert {k for k, _ in run.tags} == {ev.EVALUATION_PROGRESS_TAG}

def test_reporter_never_raises_when_mlflow_is_down():
    report = ev.make_progress_reporter(FakeRun(fail=True), total_steps=7)
    report(initial=True)
    report()  # must not raise: progress is cosmetic

def test_failed_dimension_still_counts(monkeypatch):
    """A dimension that raises must still advance progress, or the bar stalls below 100%."""
    run = FakeRun()
    report = ev.make_progress_reporter(run, total_steps=2)

    async def boom(dim):
        raise ValueError("model failed")

    async def ok(dim):
        return "score"

    async def tracked(coro):
        try:
            return await coro
        finally:
            report()

    async def go():
        return await asyncio.gather(tracked(boom("a")), tracked(ok("b")), return_exceptions=True)

    results = asyncio.run(go())

    assert isinstance(results[0], ValueError)
    assert [v for _, v in run.tags] == ["1/2", "2/2"]