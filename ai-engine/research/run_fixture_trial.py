"""
Manually trigger one full register -> evaluate -> judge -> promote cycle
against the fixed A/B bundles, without going through the FastAPI
endpoint. Reuses evaluate_sprint() and judge_and_promote_trace() unchanged --
this is a thin CLI wrapper, not a parallel reimplementation -- so a promotion
triggered here genuinely exercises the same path the live endpoint uses.

Usage:
    docker compose exec sprintsight_ai python -m research.run_ab_trial --model sprintsight-qwen
"""
import argparse
import asyncio
import json
from pathlib import Path

import mlflow
from fastapi import BackgroundTasks

from judges.promote import judge_and_promote_trace
from llmops.prompt_registry import get_production_prompt
from prompts.dimension_criteria import DIMENSIONS
from research.fixtures import FIXTURES_TEAMS
from schemas.artifact_bundle import ArtifactBundle
from services.evaluator import evaluate_sprint

DEFAULT_EXPERIMENT_NAME = "Fixture test 5/11/26"

def load_ab_bundle(ab_bundle_path: Path) -> ArtifactBundle:
    with ab_bundle_path.open() as f:
        return ArtifactBundle.model_validate(json.load(f))

async def run_fixture_trial(model_name: str, experiment_name: str = "Fixture test 2/11/26", repeats: int = 1) -> None:
    mlflow_client, background_tasks = mlflow.MlflowClient(), BackgroundTasks()
    prompts = _production_prompts()
    for bundle in FIXTURES_TEAMS:
        for i in range(repeats):
            print(f"[{i + 1}/{repeats}] Evaluating '{model_name}' against {bundle.team_id}...")
            trace_ids: list[str] = []
            assessment, prompt_versions_registered = await evaluate_sprint(bundle, model_name, experiment_name, mlflow_client, trace_ids, prompts)
            print(f"  trace_ids={trace_ids}  overall_score={assessment.overall_score}")
            trace_id = trace_ids[0]
            print(f"  trace_id={trace_id}  overall_score={assessment.overall_score}  prompts={prompt_versions_registered}")
            background_tasks.add_task(judge_and_promote_trace, experiment_name, trace_id, bundle.team_id,
                                      prompt_versions_registered, mlflow_client, bundle.sprint_id)
            # background_tasks.add_task(judge_and_promote_trace, experiment_name, trace_ids, bundle.team_id, prompt_versions_registered, mlflow_client, bundle.sprint_id)
            # print(f"  queued judging + promotion check for {bundle.team_id}")

    await background_tasks()  # outside FastAPI, queued tasks only run when awaited
    print("All evaluations + judging + promotion checks complete.")

def _bundles(dataset: str) -> list[ArtifactBundle]:
    # return [load_ab_bundle(p) for p in (CS203g6_BUNDLE_PATH, CS203jy_BUNDLE_PATH)]
    return list(FIXTURES_TEAMS)

def _production_prompts() -> dict[str, str]:
    prompts: dict[str, str] = {}
    for dim in DIMENSIONS:
        production = get_production_prompt(f"Evaluate_{dim}")
        if production is None:
            raise SystemExit(f"No production prompt for Evaluate_{dim}; run once without --baseline first.")
        prompts[dim] = production.template
    return prompts

def main() -> None:
    parser = argparse.ArgumentParser(description="Run one AB-bundle evaluation + judge + promotion cycle")
    parser.add_argument("--model", required=True, help="Ollama model tag to evaluate with")
    parser.add_argument("--experiment-name", default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--repeats", type=int, default=1)
    #parser.add_argument("--baseline", action="store_true", help="Use production prompts")
    args = parser.parse_args()
    asyncio.run(run_fixture_trial(args.model, args.experiment_name, args.repeats))
    
if __name__ == "__main__":
    main()