"""
Access rules for /insights, in both INSIGHTS_MODEs: student 403, out-of-scope 404, admin 200.
Purpose: catch regressions in the access control logic, which is complex and easy to get wrong.
The tests are parameterized to run in both blind_label and override_gate modes, which have different
access rules. The tests do not check the correctness of the returned data, only that the caller
is allowed or denied access. The data correctness is tested in test_insights_api.py.
"""

import pytest

from app.main import app
from tests.insights_support import ADMIN, API, FACULTY, STUDENT, build_env, client, headers, six


@pytest.fixture(params=["blind_label", "override_gate"])
def env(request, override_user_repository, monkeypatch):
    environment = build_env(override_user_repository, monkeypatch, request.param)
    yield environment
    environment.cleanup()

def _call(method: str, path: str, who: str | None):
    kwargs = {"headers": headers(who)} if who else {}
    if method == "put":
        kwargs["json"] = six()
    return getattr(client, method)(API + path, **kwargs)

ROUTES = [
    ("get", "/my-courses"), ("get", "/runs"), ("get", "/config"), ("get", "/override-stats"),
    ("get", "/reports/r-in/evidence"), ("put", "/reports/r-in/labels"), ("get", "/reports/r-in/reveal"),
    ("get", "/reports/r-in/trace"), ("get", "/reports/r-in/judge-status"), ("get", "/health"), 
    ("get", "/prompt-registry"), ("get", "/reports/r-in/prompts/Evaluate_testing"),
    ("get", "/prompt-registry/Evaluate_testing/1"),
]

@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_students_get_403_everywhere(env, method, path):
    assert _call(method, path, STUDENT).status_code == 403

@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_anonymous_callers_are_rejected(env, method, path):
    assert _call(method, path, None).status_code in (401, 403)

def test_every_documented_insights_route_is_in_the_matrix_and_guarded(env):
    """FastAPI hides included routers behind _IncludedRouter, so read the OpenAPI document."""
    documented = {
        (
            method,
            path.removeprefix(API)
            .replace("{report_id}", "r-in")
            .replace("{prompt_name}", "Evaluate_testing")
            .replace("{version}", "1"),
        )
        for path, operations in app.openapi()["paths"].items() if path.startswith(API)
        for method in operations
    }
    assert documented, "no /insights routes are registered"
    assert documented == set(ROUTES)
    for method, path in documented:
        assert _call(method, path, STUDENT).status_code == 403, (method, path)

@pytest.mark.parametrize("path", ["/evidence", "/reveal", "/trace", "/judge-status"])
def test_out_of_scope_and_unknown_reports_are_404(env, path):
    h = headers(FACULTY)
    assert client.get(f"{API}/reports/r-out{path}", headers=h).status_code == 404
    assert client.get(f"{API}/reports/does-not-exist{path}", headers=h).status_code == 404

def test_out_of_scope_labels_are_404_and_admin_sees_every_report(env):
    assert client.put(f"{API}/reports/r-out/labels", json=six(), headers=headers(FACULTY)).status_code == 404
    admin = headers(ADMIN)
    assert client.get(f"{API}/reports/r-out/evidence", headers=admin).status_code == 200
    assert client.get(f"{API}/reports/r-out/reveal", headers=admin).status_code == 200
    ids = {i["report_id"] for i in client.get(f"{API}/runs", headers=admin).json()["items"]}
    assert {"r-in", "r-out", "r-ovr"} <= ids

def test_instructor_only_sees_their_own_courses(env):
    ids = {i["report_id"] for i in client.get(f"{API}/runs", headers=headers(FACULTY)).json()["items"]}
    assert "r-out" not in ids and "r-in" in ids

def test_prompt_registry_is_admin_only_and_returns_no_prompt_text(env):
    assert client.get(f"{API}/prompt-registry", headers=headers(FACULTY)).status_code == 403
    body = client.get(f"{API}/prompt-registry", headers=headers(ADMIN)).json()
    assert body["available"] is True
    assert body["prompts"]
    assert all("template" not in row for row in body["prompts"])

# Regression test for a bug where the /prompt-registry endpoint returned the prompt text, which is sensitive.
def test_prompt_registry_degrades_when_mlflow_is_down(env):
    env.gateway.down = True   # FakeMlflowGateway raises MlflowUnavailable
    body = client.get(f"{API}/prompt-registry", headers=headers(ADMIN)).json()
    assert body == {"available": False, "notice": body["notice"], "prompts": []}

# Regression test for a bug where the needs_attention filter was ignored and all runs were returned.
def test_needs_attention_filter_returns_only_flagged_runs(env):
    h = headers(ADMIN)
    everything = client.get(f"{API}/runs", headers=h).json()
    flagged = client.get(f"{API}/runs", params={"needs_attention": "true"}, headers=h).json()
    assert flagged["total"] <= everything["total"]
    assert all(item["flags"] for item in flagged["items"])