"""create_llm_client honours LLM_STRUCTURED_OUTPUT_MODE (it used to hardcode JSON mode)."""

import importlib

import instructor
import pytest

from services import llm_client

ENV = "LLM_STRUCTURED_OUTPUT_MODE"


@pytest.fixture(autouse=True)
def restore_module():
    """The tests reload services.llm_client under different env values; put it back afterwards
    so later tests see the module as it is without any override."""
    yield
    # This fixture is set up before the test's monkeypatch, so it is torn down after it:
    # the env var is already restored when we reload.
    importlib.reload(llm_client)


def _client_mode(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)
    module = importlib.reload(llm_client)
    return module.create_llm_client("ollama").mode


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("json_schema", instructor.Mode.JSON_SCHEMA),
        ("JSON_SCHEMA", instructor.Mode.JSON_SCHEMA),  # value is lower-cased
        (" json_schema ", instructor.Mode.JSON_SCHEMA),  # and stripped
        ("json", instructor.Mode.JSON),
        (None, instructor.Mode.JSON_SCHEMA),  # unset -> documented default
        ("tools", instructor.Mode.JSON),  # unknown value falls back to JSON
        ("", instructor.Mode.JSON),
    ],
)
def test_structured_output_mode_is_honoured(monkeypatch, value, expected):
    assert _client_mode(monkeypatch, value) == expected
