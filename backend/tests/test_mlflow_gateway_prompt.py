"""RealMlflowGateway.get_prompt maps MLflow's PromptVersion and classifies errors by code.

The fake gateway never runs this code, which is how a bad `timezone as UTC` import got
through: these tests drive the real class with a stub client.
"""

from types import SimpleNamespace

import pytest

from app.services.insightsService.mlflow_gateway import (
    MlflowUnavailable,
    PromptNotFound,
    RealMlflowGateway,
)


def gateway_with(monkeypatch, get_prompt_version):
    gw = RealMlflowGateway("http://mlflow.invalid")
    client = SimpleNamespace(get_prompt_version=get_prompt_version)
    monkeypatch.setattr(gw, "_mlflow", lambda: (None, client))
    return gw


def version(**overrides):
    fields = {
        "template": "hello {{ name }}",
        "commit_message": "first",
        "creation_timestamp": 1_700_000_000_000,  # epoch ms: 2023-11-14
        "aliases": ["challenger"],
    }
    return SimpleNamespace(**{**fields, **overrides})


def test_maps_fields_and_formats_the_created_date(monkeypatch):
    gw = gateway_with(monkeypatch, lambda name, v: version())
    out = gw.get_prompt("Evaluate_testing", "11")
    assert out["template"] == "hello {{ name }}"
    assert out["commit_message"] == "first"
    assert out["aliases"] == ["challenger"]
    assert out["created_at"].startswith("2023-11-14")


def test_chat_style_template_is_serialised_to_text(monkeypatch):
    messages = [{"role": "system", "content": "be strict"}]
    gw = gateway_with(monkeypatch, lambda name, v: version(template=messages))
    assert '"be strict"' in gw.get_prompt("Evaluate_testing", "1")["template"]


@pytest.mark.parametrize("bad", [None, 0, "not-a-number", 10**30])
def test_a_bad_timestamp_does_not_fail_the_prompt(monkeypatch, bad):
    gw = gateway_with(monkeypatch, lambda name, v: version(creation_timestamp=bad))
    out = gw.get_prompt("Evaluate_testing", "1")
    assert out["template"] == "hello {{ name }}" and out["created_at"] is None


def test_missing_attributes_default_safely(monkeypatch):
    bare = SimpleNamespace(template="t")
    out = gateway_with(monkeypatch, lambda name, v: bare).get_prompt("Evaluate_testing", "1")
    assert out == {"template": "t", "commit_message": None, "created_at": None, "aliases": []}


def test_missing_prompt_is_identified_by_error_code(monkeypatch):
    def boom(name, v):
        error = RuntimeError("anything at all")
        error.error_code = "RESOURCE_DOES_NOT_EXIST"
        raise error

    with pytest.raises(PromptNotFound):
        gateway_with(monkeypatch, boom).get_prompt("Evaluate_testing", "99")


def test_a_network_failure_is_not_reported_as_a_missing_prompt(monkeypatch):
    def boom(name, v):
        raise ConnectionError("prompt not found on host")  # message text must not matter

    with pytest.raises(MlflowUnavailable):
        gateway_with(monkeypatch, boom).get_prompt("Evaluate_testing", "1")
