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