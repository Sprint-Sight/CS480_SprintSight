import threading
from types import SimpleNamespace

from app.services.assessmentService.service import _poll_ai_progress
from app.services.insightsService.mlflow_gateway import RealMlflowGateway

'''
Test for assessment progress polling by testing:
1. The mapping of (done, total) steps into the 70..89 range.
2. poller never writes a lower value than it has already written.
3. poller survives MLflow errors and continues to write progress.
4. That a total of 0 does not kill the poller.
5. poller stops when the stop event is set, even if an MLflow
6. real gateway parses run tags correctly and rejects bad tags.
7. poller does not write after stop is set, even if an MLflow call was in flight.
8. poller stops when the stop event is set, even if an MLflow call was in flight.
'''

class FakeJobRepo:
    def __init__(self):
        self.updates, self.events = [], []
    def update_job(self, job_id, **kw):
        self.updates.append(kw)
    def append_event(self, job_id, kind, data):
        self.events.append((kind, data))

class SeqGateway:
    """Returns items in order; once empty, stops the poller so the test finishes."""
    def __init__(self, seq, stop):
        self.seq, self.stop = list(seq), stop
    def get_eval_progress(self, correlation_id):
        if not self.seq:
            self.stop.set()
            return None
        item = self.seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

def run_poller(seq):
    stop, repo = threading.Event(), FakeJobRepo()
    _poll_ai_progress("j", "j", SeqGateway(seq, stop), repo, stop, interval=0)
    return [u["progress"] for u in repo.updates], repo

def test_steps_map_into_70_to_89_range():
    values, repo = run_poller([(0, 7), (1, 7), (3, 7), (7, 7)])
    assert values == [72, 78, 89]            # 0/7 -> 70 is not above the starting value
    assert "(3/7 steps)" in repo.events[1][1]["message"]

def test_progress_never_goes_backwards():
    values, _ = run_poller([(3, 7), (1, 7)])
    assert values == [78]

def test_survives_gateway_errors():
    values, _ = run_poller([RuntimeError("mlflow down"), (2, 7)])
    assert values == [75]

def test_zero_total_does_not_kill_the_poller():
    values, _ = run_poller([(1, 0), (1, 7)])
    assert values == [72]

def test_no_gateway_returns_immediately():
    repo = FakeJobRepo()
    _poll_ai_progress("j", "j", None, repo, threading.Event(), interval=0)
    assert repo.updates == []

def test_no_write_after_stop_even_if_mlflow_call_was_in_flight():
    stop, repo = threading.Event(), FakeJobRepo()
    class StopsMidCall:
        def get_eval_progress(self, correlation_id):
            stop.set()                        # AI call finished while we waited on MLflow
            return (3, 7)
    _poll_ai_progress("j", "j", StopsMidCall(), repo, stop, interval=0)
    assert repo.updates == []                 # the race fix from point 2

def _gateway_with(monkeypatch, runs):
    gw = RealMlflowGateway("http://mlflow.invalid")
    client = SimpleNamespace(
        search_experiments=lambda: [SimpleNamespace(experiment_id="1")],
        search_runs=lambda **kw: runs,
    )
    monkeypatch.setattr(gw, "_mlflow", lambda: (None, client))
    return gw

def _run(tag):
    return SimpleNamespace(data=SimpleNamespace(tags={"eval.progress": tag}))

def test_real_gateway_parses_run_tag(monkeypatch):
    assert _gateway_with(monkeypatch, [_run("3/7")]).get_eval_progress("job-1") == (3, 7)

def test_real_gateway_rejects_bad_tags(monkeypatch):
    for bad in ("x/y", "8/7", "1/0", ""):
        assert _gateway_with(monkeypatch, [_run(bad)]).get_eval_progress("job-1") is None

def test_real_gateway_no_matching_run(monkeypatch):
    assert _gateway_with(monkeypatch, []).get_eval_progress("job-1") is None

# --- the bar keeps moving while the engine is busy inside one step -------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class TimedGateway:
    """One engine report per poll, 30 simulated seconds apart. None = the engine has not started
    the run; an Exception = MLflow was unreachable for that poll."""

    def __init__(self, clock: Clock, stop: threading.Event, reports) -> None:
        self.clock, self.stop, self.reports = clock, stop, list(reports)

    def get_eval_progress(self, correlation_id):
        if not self.reports:
            self.stop.set()
            return None
        self.clock.now += 30
        report = self.reports.pop(0)
        if isinstance(report, Exception):
            raise report
        return report


def timed_poll(reports, expected_step_seconds=120.0):
    clock, stop, repo = Clock(), threading.Event(), FakeJobRepo()
    gateway = TimedGateway(clock, stop, reports)
    _poll_ai_progress(
        "j", "j", gateway, repo, stop, interval=0, expected_step_seconds=expected_step_seconds, clock=clock
    )
    return [u["progress"] for u in repo.updates], repo


def test_the_bar_creeps_within_a_step_but_never_reaches_the_next_one():
    values, repo = timed_poll([(0, 7)] * 40)  # twenty minutes inside the first step

    assert values == [71, 72]  # climbs, then holds just short of the real step 1 (72)
    assert all(70 < v <= 72 for v in values)
    assert all(kind == "progress" for kind, _ in repo.events)


def test_a_real_step_never_moves_the_bar_backwards_and_creeping_resumes_after_it():
    values, _ = timed_poll([(0, 7)] * 10 + [(1, 7)] * 10 + [(2, 7)])

    assert values == sorted(values) and len(set(values)) == len(values)  # only ever up
    assert values[-1] == 75  # the engine's own report for 2/7 is 70 + int(19 * 2 / 7)
    assert 73 in values or 74 in values  # it kept moving inside the second step


def test_the_bar_does_not_move_before_the_engine_has_started_the_run():
    values, repo = timed_poll([None] * 20)  # e.g. waiting for the model slot

    assert values == [] and repo.events == []


def test_a_flaky_mlflow_does_not_freeze_the_bar():
    values, _ = timed_poll([(0, 7), RuntimeError("mlflow down"), RuntimeError("mlflow down")] + [None] * 8)

    assert values[-1] == 72  # carried on creeping from the last report


def test_the_step_time_is_learned_from_the_steps_that_finished():
    # Step 1 took 30 s, far less than the 120 s guess, so step 2 is expected to be quick too.
    from app.services.assessmentService.service import ai_stage_percent

    learned, _ = timed_poll([(0, 7), (1, 7), (1, 7)])

    # 30 s into step 2: 74 with the learned 30 s step, but only 73 with the 120 s guess
    assert learned == [72, 74]
    assert ai_stage_percent(1, 7, 30, 120) == 73


def test_the_percentage_is_exact_at_step_boundaries_and_capped_inside_steps():
    from app.services.assessmentService.service import ai_stage_percent

    assert ai_stage_percent(0, 7, 0, 120) == 70
    assert ai_stage_percent(3, 7, 0, 120) == 78  # the engine's own value, as before
    assert ai_stage_percent(0, 7, 10**9, 120) == 72  # held below step 1's 72.7 boundary
    assert ai_stage_percent(6, 7, 10**9, 120) <= 89
    assert ai_stage_percent(7, 7, 10**9, 120) == 89  # all steps done: no creeping past the stage
