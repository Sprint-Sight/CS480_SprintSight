"""App startup must not register prompt versions and must survive MLflow being down."""

import asyncio

import pytest

import main


@pytest.fixture
def stubbed_startup(monkeypatch):
    """Replace the lifespan's collaborators; returns the list of calls they received."""
    calls: list[str] = []
    monkeypatch.setattr(main, "create_llm_client", lambda: calls.append("llm_client") or object())
    monkeypatch.setattr(main, "start_judge_worker", lambda: calls.append("judge_start"))
    monkeypatch.setattr(main, "stop_judge_worker", lambda: calls.append("judge_stop"))
    monkeypatch.setattr(main, "register_all_dimension_prompts", lambda: calls.append("dimension_prompts"))
    monkeypatch.setattr(main, "configure_mlflow", lambda: calls.append("configure_mlflow"))
    return calls


def _run_lifespan() -> None:
    async def go() -> None:
        async with main.lifespan(main.app):
            pass

    asyncio.run(go())


def test_startup_configures_mlflow_without_registering_a_bootstrap_prompt(stubbed_startup, monkeypatch) -> None:
    registered: list[str] = []
    monkeypatch.setattr("mlflow.genai.register_prompt", lambda *a, **k: registered.append("register"))

    _run_lifespan()

    assert registered == []
    assert stubbed_startup == ["configure_mlflow", "dimension_prompts", "llm_client", "judge_start", "judge_stop"]


def test_startup_survives_mlflow_configuration_failure(stubbed_startup, monkeypatch, caplog) -> None:
    def boom() -> None:
        raise ConnectionError("mlflow_service unreachable")

    monkeypatch.setattr(main, "configure_mlflow", boom)

    _run_lifespan()  # must not raise

    assert "Failed to configure MLflow" in caplog.text
    assert "llm_client" in stubbed_startup and "judge_start" in stubbed_startup


def test_startup_survives_prompt_registry_outage(stubbed_startup, monkeypatch) -> None:
    def boom() -> None:
        raise ConnectionError("mlflow_service unreachable")

    monkeypatch.setattr(main, "register_all_dimension_prompts", boom)

    _run_lifespan()  # must not raise

    assert "llm_client" in stubbed_startup and "judge_start" in stubbed_startup
