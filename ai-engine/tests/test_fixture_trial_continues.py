"""One team whose every dimension fails must not abort the fixture trial or skip the judge queue."""

import asyncio
from types import SimpleNamespace

from mlflow.exceptions import MlflowException

from research.trials import run_fixture_trial as trial
from schemas.all_dimensions_failed_error import AllDimensionsFailedError


def _bundle(team_id: str) -> SimpleNamespace:
    return SimpleNamespace(team_id=team_id, sprint_id=f"{team_id}-s1")


def _run_trial(monkeypatch, failing_error: Exception):
    queued, evaluated = [], []

    class FakeBackgroundTasks:
        awaited = 0

        def add_task(self, fn, *args):
            queued.append(args[2])  # team_id

        async def __call__(self):
            type(self).awaited += 1

    async def fake_evaluate_sprint(bundle, model_name, experiment_name, client, trace_ids, prompts):
        evaluated.append(bundle.team_id)
        if bundle.team_id == "team-1":
            raise failing_error
        trace_ids.append(f"tr-{bundle.team_id}")
        return SimpleNamespace(overall_score=7.0), {"Evaluate_testing": 1}

    monkeypatch.setattr(trial, "FIXTURES_TEAMS", [_bundle("team-1"), _bundle("team-2")])
    monkeypatch.setattr(trial, "BackgroundTasks", FakeBackgroundTasks)
    monkeypatch.setattr(trial, "_production_prompts", dict)
    monkeypatch.setattr(trial, "evaluate_sprint", fake_evaluate_sprint)
    monkeypatch.setattr(trial.mlflow, "MlflowClient", lambda: SimpleNamespace(set_trace_tag=lambda *a: None))
    monkeypatch.setattr(trial.mlflow, "flush_trace_async_logging", lambda: None)

    asyncio.run(trial.run_fixture_trial("some-model"))
    return evaluated, queued, FakeBackgroundTasks.awaited


def test_an_all_dimensions_failure_skips_only_that_team(monkeypatch) -> None:
    evaluated, queued, awaited = _run_trial(monkeypatch, AllDimensionsFailedError({"testing": "timeout: no answer"}))

    assert evaluated == ["team-1", "team-2"]  # the loop went on to team 2
    assert queued == ["team-2"]               # only the healthy team's trace is judged
    assert awaited == 1                       # and the queue still ran


def test_an_mlflow_error_skips_only_that_team(monkeypatch) -> None:
    evaluated, queued, awaited = _run_trial(monkeypatch, MlflowException("tracking server unreachable"))

    assert evaluated == ["team-1", "team-2"]
    assert queued == ["team-2"]
    assert awaited == 1
