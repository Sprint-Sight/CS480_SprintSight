"""A judge job that is skipped or abandoned leaves a mark on its trace, so the backend can show
"failed: <reason>" instead of a trace that looks like the judge never ran (stale)."""

from types import SimpleNamespace

from evaluation.online import promote
from evaluation.online.job_queue import JudgeJobQueue
from evaluation.online.scheduler import JudgeWorker, ModelSlotArbiter
from prompts.dimension_criteria import DIMENSIONS


def make_worker(tmp_path, runner, on_dead, *, lease_seconds=3600.0, clock=None):
    kwargs = {"clock": clock} if clock else {}
    queue = JudgeJobQueue(tmp_path / "jobs.sqlite3", max_attempts=2, lease_seconds=lease_seconds, **kwargs)
    queue.enqueue(trace_id="tr-1", experiment_name="e", team_id="t", sprint_id="s", prompt_versions={})
    worker = JudgeWorker(
        queue, runner, ModelSlotArbiter(), retry_delay_seconds=0, slot_wait_seconds=0.05, on_dead=on_dead
    )
    return worker, queue


def test_a_job_that_runs_out_of_attempts_tags_its_trace_with_the_failure_class(tmp_path) -> None:
    tagged: list[tuple[str, str]] = []

    def boom(job) -> None:
        raise ConnectionError("ollama down")

    worker, _ = make_worker(tmp_path, boom, lambda trace, reason: tagged.append((trace, reason)))

    worker.run_once()
    assert tagged == []  # first failure is retried, not abandoned
    worker.run_once()

    assert tagged == [("tr-1", "infra_unavailable")]


def test_tagging_failure_never_breaks_the_worker(tmp_path) -> None:
    def broken_tagger(trace, reason) -> None:
        raise RuntimeError("mlflow down")

    def boom(job) -> None:
        raise TimeoutError("slow")

    worker, queue = make_worker(tmp_path, boom, broken_tagger)
    worker.run_once()
    assert worker.run_once() is True
    assert queue.stats()["dead"] == 1


def test_a_crash_looping_job_is_tagged_when_the_queue_gives_up_on_it(tmp_path) -> None:
    class Clock:
        now = 1_000.0

        def __call__(self) -> float:
            return self.now

    clock, tagged = Clock(), []
    worker, queue = make_worker(
        tmp_path, lambda job: None, lambda trace, reason: tagged.append((trace, reason)),
        lease_seconds=10, clock=clock,
    )
    for _ in range(2):  # claimed twice, and the worker "dies" each time (lease expires)
        assert queue.claim_next() is not None
        clock.now += 11

    assert queue.claim_next() is None  # attempts exhausted: now dead
    worker._drain_dead()

    assert tagged == [("tr-1", "retries_exhausted")]


def test_a_trace_with_every_dimension_failed_is_tagged_skipped(monkeypatch) -> None:
    root = SimpleNamespace(parent_id=None, outputs={"failed_dimensions": list(DIMENSIONS)})
    trace = SimpleNamespace(data=SimpleNamespace(spans=[root]))
    tags: list[tuple[str, str, str]] = []

    class Client:
        def get_trace(self, trace_id):
            return trace

        def set_trace_tag(self, trace_id, key, value):
            tags.append((trace_id, key, value))

    monkeypatch.setattr(promote.mlflow, "flush_trace_async_logging", lambda: None)
    monkeypatch.setattr(promote, "run_judge_evaluation", lambda *a, **k: (_ for _ in ()).throw(AssertionError("judge must not run")))

    promote.run_judge_and_promotion("exp", "tr-9", "team", {}, Client(), "s1")

    assert tags == [("tr-9", "judge.skipped", "all_dimensions_failed")]
