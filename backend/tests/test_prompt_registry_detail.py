"""Admin prompt-registry drawer: template, aliases and a diff against the previous version."""

import pytest
from fastapi import HTTPException

from app.services.insightsService.fake_gateway import FakeMlflowGateway
from app.services.insightsService.service import MLFLOW_DOWN_NOTICE, registry_prompt_detail

NAME = "Evaluate_testing"


def prompt(template: str, aliases=()):
    return {"template": template, "commit_message": "msg", "created_at": None, "aliases": list(aliases)}


@pytest.fixture
def gateway():
    fake = FakeMlflowGateway()
    fake.prompts[(NAME, "1")] = prompt("line one\nline two", ["production"])
    fake.prompts[(NAME, "2")] = prompt("line one\nline 2 changed", ["challenger"])
    return fake


def test_first_version_has_no_diff(gateway):
    detail = registry_prompt_detail(gateway, NAME, 1)
    assert detail["available"] is True
    assert detail["template"] == "line one\nline two"
    assert detail["aliases"] == ["production"]
    assert detail["diff"] is None


def test_later_version_diffs_against_the_previous_one(gateway):
    detail = registry_prompt_detail(gateway, NAME, 2)
    assert "-line two" in detail["diff"] and "+line 2 changed" in detail["diff"]
    assert detail["diff"].startswith("--- v1")


def test_identical_templates_give_no_diff(gateway):
    gateway.prompts[(NAME, "3")] = prompt("line one\nline 2 changed")
    assert registry_prompt_detail(gateway, NAME, 3)["diff"] is None


def test_unknown_prompt_name_is_404(gateway):
    with pytest.raises(HTTPException) as error:
        registry_prompt_detail(gateway, "Evaluate_secrets", 1)
    assert error.value.status_code == 404


def test_missing_version_is_404(gateway):
    with pytest.raises(HTTPException) as error:
        registry_prompt_detail(gateway, NAME, 99)
    assert error.value.status_code == 404


def test_version_zero_is_404(gateway):
    with pytest.raises(HTTPException) as error:
        registry_prompt_detail(gateway, NAME, 0)
    assert error.value.status_code == 404


def test_mlflow_down_degrades_to_a_notice(gateway):
    gateway.down = True
    detail = registry_prompt_detail(gateway, NAME, 2)
    assert detail["available"] is False and detail["template"] is None
    assert detail["notice"] == MLFLOW_DOWN_NOTICE


def test_missing_previous_version_still_returns_the_template(gateway):
    gateway.prompts[(NAME, "5")] = prompt("only this")
    detail = registry_prompt_detail(gateway, NAME, 5)    # v4 was never registered
    assert detail["available"] is True and detail["diff"] is None
