from types import SimpleNamespace

from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_DOES_NOT_EXIST

from llmops import review_queue

'''
Tests for the review_queue module. These tests are not exhaustive, 
but they cover the main logic of adding traces to a review queue and handling errors.
'''

def _fake_client(monkeypatch, exp_id="17"):
    trace = SimpleNamespace(info=SimpleNamespace(experiment_id=exp_id))
    monkeypatch.setattr(review_queue.mlflow, "MlflowClient",
                        lambda: SimpleNamespace(get_trace=lambda _id: trace))

def test_creates_one_custom_queue_and_attaches(monkeypatch):
    _fake_client(monkeypatch)
    calls = {}
    def missing(**kw):
        raise MlflowException("no", error_code=RESOURCE_DOES_NOT_EXIST)
    monkeypatch.setattr(review_queue, "get_review_queue", missing)
    monkeypatch.setattr(review_queue, "create_review_queue",
        lambda name, **kw: calls.update(created=(name, kw)) or SimpleNamespace(queue_id="q1"))
    monkeypatch.setattr(review_queue, "add_items_to_review_queue",
        lambda **kw: calls.update(added=kw))
    review_queue.add_to_review_queue("review_queue_tr-1", ["tr-1"])
    assert calls["created"] == ("flagged_runs", {"queue_type": "custom", "experiment_id": "17"})
    assert calls["added"] == {"queue_id": "q1", "item_ids": ["tr-1"]}

def test_failure_is_logged_not_raised(monkeypatch):
    _fake_client(monkeypatch)
    def boom(**kw):
        raise RuntimeError("MLflow down")
    monkeypatch.setattr(review_queue, "get_review_queue", boom)
    review_queue.add_to_review_queue("x", ["tr-1"])  # must not raise