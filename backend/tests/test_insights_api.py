"""Tier 1 (INSIGHTS_MODE=blind_label): blind labelling, reveal, sync and degraded mode."""

import pytest

from app.services.insightsService.label_sync import sync_pending_labels
from tests.insights_support import (
    ADMIN,
    API,
    FACULTY,
    build_env,
    client,
    headers,
    six,
)


@pytest.fixture
def env(override_user_repository, monkeypatch):
    environment = build_env(override_user_repository, monkeypatch, "blind_label")
    yield environment
    environment.cleanup()


def test_runs_hide_scores_until_all_six_labelled(env):
    h = headers(FACULTY)
    items = {i["report_id"]: i for i in client.get(f"{API}/runs", headers=h).json()["items"]}
    assert "r-out" not in items  # course scope
    assert items["r-in"]["ai_score"] is None and items["r-in"]["ai_score_hidden"] is True
    assert items["r-in"]["citation_check"] is None and items["r-in"]["insights_unlocked"] is False
    assert client.put(f"{API}/reports/r-in/labels", json=six(), headers=h).status_code == 200
    env.insights.set_judge_status("r-in", "complete", {"grounded_rate": 0.75, "hallucination_rate": 0.25})
    items = {i["report_id"]: i for i in client.get(f"{API}/runs", headers=h).json()["items"]}
    assert items["r-in"]["ai_score"] == 7.0 and items["r-in"]["labels_done"] == 6
    assert items["r-in"]["citation_check"]["status"] == "flagged"


def test_evidence_contains_no_ai_fields(env):
    body = client.get(f"{API}/reports/r-in/evidence", headers=headers(FACULTY)).json()

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)

    forbidden = {"ai_score", "justification", "rubric_scores", "team_score", "judge", "tiles",
                 "overall_ai_score", "evidence_citations", "judge_summary"}
    assert not forbidden & set(keys(body))
    assert body["can_reveal"] is False and body["labels_done"] == 0


def test_label_validation(env):
    h = headers(FACULTY)
    bad_score = {"labels": [{"dimension": "testing", "score": 11}]}
    long_reason = {"labels": [{"dimension": "testing", "score": 5, "reason": "x" * 1001}]}
    dupes = {"labels": [{"dimension": "testing", "score": 5}, {"dimension": "testing", "score": 6}]}
    for payload in (bad_score, long_reason, dupes):
        assert client.put(f"{API}/reports/r-in/labels", json=payload, headers=h).status_code == 422
    assert client.put(f"{API}/reports/r-in/labels", json=six(), headers=headers(ADMIN)).status_code == 403


def test_reveal_requires_six_then_compares_and_locks(env):
    h = headers(FACULTY)
    assert client.get(f"{API}/reports/r-in/reveal", headers=h).status_code == 409
    client.put(f"{API}/reports/r-in/labels", json={"labels": six()["labels"][:5]}, headers=h)
    assert client.get(f"{API}/reports/r-in/reveal", headers=h).status_code == 409
    client.put(f"{API}/reports/r-in/labels", json=six(8), headers=h)
    body = client.get(f"{API}/reports/r-in/reveal", headers=h).json()
    assert body["comparison"] == "blind_label"
    testing = next(d for d in body["dimensions"] if d["dimension"] == "testing")
    assert (testing["ai_score"], testing["your_score"], testing["diff"], testing["within_1"]) == (6.0, 8, 2.0, False)
    assert body["judge"]["available"] is True and body["judge_status"] == "complete"
    assert len(body["judge"]["tiles"]) == 6
    assert body["judge"]["unaccepted_citations"][0]["claim"] == "abc123 | Added tests"
    assert body["prompt_versions"] == [{"name": "Evaluate_testing", "version": "3"}]
    assert client.get(f"{API}/reports/r-in/trace", headers=h).json()["llm_call_count"] == 7
    assert client.put(f"{API}/reports/r-in/labels", json=six(3), headers=h).status_code == 409  # locked


def test_label_after_score_exposure_is_not_blind(env):
    env.insights.stamp_view("r-in", "u-faculty-1", score_seen=True)  # e.g. opened the old report page
    response = client.put(f"{API}/reports/r-in/labels", json={"labels": six()["labels"][:2]},
                          headers=headers(FACULTY))
    assert response.json()["is_blind"] is False
    assert all(not label.is_blind for label in env.insights.labels_for("r-in", "u-faculty-1"))


def test_snapshot_uses_original_ai_score_not_override(env):
    client.put(f"{API}/reports/r-ovr/labels", json=six(), headers=headers(FACULTY))
    assert {label.ai_score_snapshot for label in env.insights.labels_for("r-ovr", "u-faculty-1")} == {5.0}


def test_overridden_report_reveals_scores_on_the_same_scale_as_the_ai(env):
    """Regression: typed override fields are stored 0-100; the reveal must show 0-10."""
    h = headers(FACULTY)
    assert client.patch("/api/v1/assessments/reports/r-in", json={
        "requirements_score": 50.0, "code_quality_score": 70.0, "documentation_score": 70.0,
        "collaboration_score": 70.0, "requirements_justification": "x", "code_quality_justification": "x",
        "documentation_justification": "x", "collaboration_justification": "x",
    }, headers=h).status_code == 200
    client.put(f"{API}/reports/r-in/labels", json=six(), headers=h)
    body = client.get(f"{API}/reports/r-in/reveal", headers=h).json()
    requirements = next(d for d in body["dimensions"] if d["dimension"] == "requirements")
    assert requirements["ai_score"] == 7.0 and requirements["ai_score_current"] == 5.0
    assert requirements["overridden"] is True


def test_degraded_mode_keeps_scores_and_shows_notice(env):
    h = headers(FACULTY)
    client.put(f"{API}/reports/r-in/labels", json=six(), headers=h)
    env.gateway.down = True
    body = client.get(f"{API}/reports/r-in/reveal", headers=h).json()
    assert body["judge"]["available"] is False and "unreachable" in body["judge"]["notice"]
    assert body["dimensions"][0]["ai_score"] == 7.0
    assert client.get(f"{API}/runs", headers=h).status_code == 200


def test_health_is_admin_only(env):
    assert client.get(f"{API}/health", headers=headers(FACULTY)).status_code == 403
    body = client.get(f"{API}/health", headers=headers(ADMIN)).json()
    assert body["mlflow"]["versions_match"] is True and body["overrides_pending_sync"] == 0


def test_sync_is_idempotent_when_a_response_is_lost(env):
    env.gateway.lose_next_response = 1  # first write lands in MLflow but the backend sees an error
    client.put(f"{API}/reports/r-in/labels", json=six(), headers=headers(FACULTY))  # background sync
    assert env.insights.count_pending_labels() == 1
    sync_pending_labels(env.insights, env.gateway, min_age_seconds=0)
    assert env.insights.count_pending_labels() == 0
    assert len(env.gateway.labels["tr-1"]) == 6  # no duplicate
