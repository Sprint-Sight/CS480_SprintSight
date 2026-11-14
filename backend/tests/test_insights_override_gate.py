"""INSIGHTS_MODE=override_gate: Insights unlock once an instructor saves an override."""

import pytest

from app.services.insightsService.label_sync import sync_pending_overrides
from app.services.insightsService.override_stats import NOTICE, override_stats
from tests.insights_support import (
    ADMIN,
    AI_SCORES,
    API,
    FACULTY,
    build_env,
    client,
    headers,
    make_report,
    override_patch,
    six,
)

PATCH_URL = "/api/v1/assessments/reports/r-in"


@pytest.fixture
def env(override_user_repository, monkeypatch):
    environment = build_env(override_user_repository, monkeypatch, "override_gate")
    yield environment
    environment.cleanup()


def _reveal(report_id="r-in", who=FACULTY):
    return client.get(f"{API}/reports/{report_id}/reveal", headers=headers(who))


def test_config_reports_the_mode(env):
    assert client.get(f"{API}/config", headers=headers(FACULTY)).json() == {"mode": "override_gate"}


def test_reveal_and_trace_are_locked_until_an_override_is_saved(env):
    h = headers(FACULTY)
    for path in ("reveal", "trace"):
        response = client.get(f"{API}/reports/r-in/{path}", headers=h)
        assert response.status_code == 409
        assert "Assessment Report" in response.json()["error"]["message"]
    assert _reveal(who=ADMIN).status_code == 200  # admin sees everything, as before
    assert client.get(f"{API}/reports/r-in/judge-status", headers=h).status_code == 200  # status only


def test_runs_show_the_score_but_gate_judge_checks(env):
    h = headers(FACULTY)
    env.insights.set_judge_status("r-in", "complete", {"grounded_rate": 0.75, "hallucination_rate": 0.25})
    before = {i["report_id"]: i for i in client.get(f"{API}/runs", headers=h).json()["items"]}["r-in"]
    assert before["ai_score"] == 7.0 and before["ai_score_hidden"] is False
    assert before["insights_unlocked"] is False and before["citation_check"] is None
    assert client.patch(PATCH_URL, json=override_patch(), headers=h).status_code == 200
    after = {i["report_id"]: i for i in client.get(f"{API}/runs", headers=h).json()["items"]}["r-in"]
    assert after["insights_unlocked"] is True and after["overridden"] is True
    assert after["citation_check"]["status"] == "flagged"


def test_override_unlocks_and_compares_on_a_single_scale(env):
    h = headers(FACULTY)
    assert client.patch(PATCH_URL, json=override_patch(requirements=50.0, testing=4.0), headers=h).status_code == 200
    response = _reveal()
    assert response.status_code == 200
    body = response.json()
    assert body["comparison"] == "override"
    rows = {d["dimension"]: d for d in body["dimensions"]}
    assert (rows["requirements"]["ai_score"], rows["requirements"]["your_score"], rows["requirements"]["diff"]) == (7.0, 5.0, -2.0)
    assert (rows["testing"]["ai_score"], rows["testing"]["your_score"], rows["testing"]["diff"]) == (6.0, 4.0, -2.0)
    assert rows["code_quality"]["diff"] == 0 and rows["code_quality"]["overridden"] is False
    assert rows["requirements"]["overridden"] is True
    assert all(d["within_1"] is None for d in body["dimensions"])  # never an accuracy claim
    assert body["judge"]["available"] is True and len(body["judge"]["tiles"]) == 6
    assert client.get(f"{API}/reports/r-in/trace", headers=h).status_code == 200


def test_save_without_changes_still_unlocks_but_records_no_change(env):
    h = headers(FACULTY)
    assert client.patch(PATCH_URL, json=override_patch(requirements=70.0, testing=6.0), headers=h).status_code == 200
    assert _reveal().status_code == 200
    rows = env.insights.overrides_for("r-in")
    assert rows and all(not row.changed and row.sync_status == "not_needed" for row in rows)
    assert env.insights.count_pending_overrides() == 0
    stats = override_stats([env.assessments.get_report("r-in")])
    assert stats["reports_overridden"] == 1 and stats["reports_with_changes"] == 0
    assert all(d["changed"] == 0 for d in stats["by_dimension"])


def test_blind_labelling_is_switched_off(env):
    assert client.put(f"{API}/reports/r-in/labels", json=six(), headers=headers(FACULTY)).status_code == 409


def test_overrides_sync_to_mlflow_once_even_if_a_response_is_lost(env):
    h = headers(FACULTY)
    client.patch(PATCH_URL, json=override_patch(requirements=50.0, testing=4.0), headers=h)
    assert env.insights.count_pending_overrides() == 2  # requirements and testing changed
    env.gateway.lose_next_response = 1
    sync_pending_overrides(env.insights, env.gateway)  # the first write lands but the caller sees an error
    sync_pending_overrides(env.insights, env.gateway)  # retried: found by feedback id, not re-written
    assert env.insights.count_pending_overrides() == 0
    stored = env.gateway.labels["tr-1"]
    assert sorted(v["name"] for v in stored.values()) == [
        "sprintsight.override.requirements", "sprintsight.override.testing"]
    requirements = next(v for v in stored.values() if v["dimension"] == "requirements")
    assert requirements["metadata"]["blind"] == "false"
    assert requirements["metadata"]["ai_score_original"] == "7"
    assert requirements["score"] == 5.0


def test_reverting_updates_the_same_mlflow_assessment(env):
    h = headers(FACULTY)
    client.patch(PATCH_URL, json=override_patch(requirements=50.0, testing=4.0), headers=h)
    sync_pending_overrides(env.insights, env.gateway)
    ids = set(env.gateway.labels["tr-1"])
    client.patch(PATCH_URL, json=override_patch(requirements=70.0, testing=4.0), headers=h)  # back to the AI score
    assert env.insights.count_pending_overrides() == 1
    sync_pending_overrides(env.insights, env.gateway)
    assert set(env.gateway.labels["tr-1"]) == ids  # updated in place, no new assessment
    requirements = next(v for v in env.gateway.labels["tr-1"].values() if v["dimension"] == "requirements")
    assert requirements["score"] == 7.0


def test_a_failure_recording_the_override_does_not_break_the_editor(env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("insights down")

    monkeypatch.setattr(env.insights, "upsert_overrides", boom)
    assert client.patch(PATCH_URL, json=override_patch(), headers=headers(FACULTY)).status_code == 200


def test_override_stats_route_never_reports_accuracy(env):
    h = headers(FACULTY)
    client.patch(PATCH_URL, json=override_patch(requirements=50.0, testing=4.0), headers=h)
    body = client.get(f"{API}/override-stats", headers=h).json()
    assert body["notice"] == NOTICE and "not a measure of AI accuracy" in body["notice"]
    assert not {"exact_match", "within_1", "within_1_rate", "accuracy"} & set(body)
    assert all("within_1" not in row for row in body["by_dimension"])


def test_override_stats_match_a_hand_computed_fixture():
    def overridden(requirements, testing):
        report = make_report("x", "c", "p", original=dict(AI_SCORES), override=True)
        # requirements is a typed field on 0-100; testing lives in rubric_scores on 1-10
        return report.model_copy(update={
            "requirements_score": requirements,
            "rubric_scores": {**report.rubric_scores,
                              "testing": report.rubric_scores["testing"].model_copy(update={"score": testing})},
        })

    reports = [
        overridden(50.0, 4.0),   # requirements 7 -> 5 (-2), testing 6 -> 4 (-2)
        overridden(60.0, 6.0),   # requirements 7 -> 6 (-1), testing unchanged
        make_report("y", "c", "p", original=dict(AI_SCORES)),            # never saved: not agreement
        make_report("z", "c", "p", original=dict(AI_SCORES), override=True),  # saved, nothing changed
    ]
    stats = override_stats(reports)
    assert (stats["reports"], stats["reports_overridden"], stats["override_rate"]) == (4, 3, 0.75)
    assert stats["reports_with_changes"] == 2
    rows = {r["dimension"]: r for r in stats["by_dimension"]}
    assert rows["requirements"]["overrides_saved"] == 3 and rows["requirements"]["changed"] == 2
    assert rows["requirements"]["mean_adjustment"] == -1.5 and rows["requirements"]["direction"] == "lowered"
    assert rows["testing"]["changed"] == 1 and rows["testing"]["mean_abs_adjustment"] == 2.0
    assert rows["cicd"]["changed"] == 0 and rows["cicd"]["direction"] is None


def test_a_dimension_the_ai_failed_is_left_out_of_the_comparison():
    original = {k: v for k, v in AI_SCORES.items() if k != "cicd"}  # the AI did not assess cicd
    report = make_report("x", "c", "p", original=original, override=True)
    from app.services.insightsService.service import override_comparison

    row = next(r for r in override_comparison(report) if r["dimension"] == "cicd")
    assert row["ai_score"] is None and row["adjustment"] is None and row["changed"] is False
    assert not any(d["dimension"] == "cicd" for d in override_stats([report])["by_dimension"] if d["changed"])
