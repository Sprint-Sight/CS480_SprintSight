"""run_grounding_judge reports progress after every batch, and once at the start (0 done)."""

import asyncio
from types import SimpleNamespace

from evaluation.judges import citation_grounding as cg


def test_run_grounding_judge_reports_each_batch(monkeypatch):
    calls: list[tuple[int, int]] = []

    async def fake_context(*args, **kwargs):
        return 16384

    async def fake_batch(*args, **kwargs):
        return cg.GroundingVerdict(citation_verdicts=[], judge_notes="stub verdict, no claims")

    three_batches = [SimpleNamespace(evidence_level=1, ids=["C1"]) for _ in range(3)]
    monkeypatch.setattr(cg, "_judge_context", fake_context)
    monkeypatch.setattr(cg, "plan_batches", lambda *args, **kwargs: three_batches)
    monkeypatch.setattr(cg, "_judge_batch", fake_batch)

    asyncio.run(
        cg.run_grounding_judge(None, {}, "m", on_progress=lambda done, total: calls.append((done, total)))
    )

    # (0, 3) first: it also clears a stale tag left by an earlier run on the same trace.
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]