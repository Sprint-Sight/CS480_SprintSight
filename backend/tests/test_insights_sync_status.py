import pytest

from app.services.insightsService.label_sync import sync_pending_overrides
from tests.insights_support import API, FACULTY, build_env, client, headers, override_patch

# Per-report MLflow sync status in GET /insights/runs (override_gate mode)

@pytest.fixture
def env(override_user_repository, monkeypatch):
    environment = build_env(override_user_repository, monkeypatch, "override_gate")
    yield environment
    environment.cleanup()

def _sync(report_id):
    items = client.get(f"{API}/runs", headers=headers(FACULTY)).json()["items"]
    return next(i for i in items if i["report_id"] == report_id)["override_sync"]

def test_pending_then_synced(env):
    assert _sync("r-in") is None  # nothing saved yet
    client.patch("/api/v1/assessments/reports/r-in", json=override_patch(), headers=headers(FACULTY))
    assert _sync("r-in") == "pending"
    sync_pending_overrides(env.insights, env.gateway)
    assert _sync("r-in") == "synced"

def test_stays_pending_while_mlflow_is_down(env):
    client.patch("/api/v1/assessments/reports/r-in", json=override_patch(), headers=headers(FACULTY))
    env.gateway.down = True
    sync_pending_overrides(env.insights, env.gateway)
    assert _sync("r-in") == "pending"  # retried on the next tick
    env.gateway.down = False
    sync_pending_overrides(env.insights, env.gateway)
    assert _sync("r-in") == "synced"

def test_report_without_a_trace_shows_no_trace(env):
    client.patch("/api/v1/assessments/reports/r-ovr", json=override_patch(), headers=headers(FACULTY))
    sync_pending_overrides(env.insights, env.gateway)
    assert _sync("r-ovr") == "no_trace"

def test_a_save_with_no_changes_has_nothing_to_sync(env):
    client.patch("/api/v1/assessments/reports/r-in",
                 json=override_patch(requirements=70.0, testing=6.0), headers=headers(FACULTY))
    assert _sync("r-in") == "not_needed"