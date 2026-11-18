"""
Manually trigger one full register -> evaluate -> judge -> promote cycle
against the five synthetic_v2 teams (evaluation/benchmarks/synthetic_v2.py),
without going through the FastAPI endpoint. Reuses evaluate_sprint() and judge_and_promote_trace() unchanged --
this is a thin CLI wrapper, not a parallel reimplementation -- so a promotion
triggered here genuinely exercises the same path the live endpoint uses.

Usage:
    for m in sprintsight-qwen25-32b sprintsight-qwen sprintsight-gemma sprintsight-r1-32b sprintsight-coder-32b; do
        docker compose exec sprintsight_ai python -m research.trials.run_fixture_trial --model "$m"
    done

Add --baseline to grade with the registered production prompts instead of the prompts in the code.
"""
import argparse
import asyncio
import json
from pathlib import Path

import mlflow
from fastapi import BackgroundTasks
from mlflow.exceptions import MlflowException

from evaluation.benchmarks.synthetic_v2 import FIXTURES_TEAMS
from evaluation.online.promote import judge_and_promote_trace
from llmops.console import use_utf8_streams
from llmops.prompt_registry import get_production_prompt
from prompts.dimension_criteria import DIMENSIONS
from schemas.all_dimensions_failed_error import AllDimensionsFailedError
from schemas.artifact_bundle import ArtifactBundle
from services.evaluator import evaluate_sprint

DEFAULT_EXPERIMENT_NAME = "openai judges fixtures test 4"

def load_ab_bundle(ab_bundle_path: Path) -> ArtifactBundle:
    with ab_bundle_path.open() as f:
        return ArtifactBundle.model_validate(json.load(f))

async def run_fixture_trial(model_name: str, experiment_name: str = "Fixture test", repeats: int = 1, baseline: bool = False) -> None:
    mlflow_client, background_tasks = mlflow.MlflowClient(), BackgroundTasks()
    # None = the prompts in the code, which register as challengers; --baseline grades with
    # what is promoted to production, to measure a challenger against it.
    prompts = _production_prompts() if baseline else None
    for bundle in FIXTURES_TEAMS:
        for i in range(repeats):
            print(f"[{i + 1}/{repeats}] Evaluating '{model_name}' against {bundle.team_id}...")
            trace_ids: list[str] = []  # fresh per run so a judge task only sees its own traces
            try:
                assessment, prompt_versions_registered = await evaluate_sprint(bundle, model_name, experiment_name, mlflow_client, trace_ids, prompts)
            except (AllDimensionsFailedError, MlflowException, RuntimeError, ValueError, OSError, KeyError, TypeError, AttributeError) as e:
                print(f"  Error evaluating '{model_name}' against {bundle.team_id}: {e}, SKIPPED")
                continue
            print(f"  trace_ids={trace_ids}  overall_score={assessment.overall_score}")
            trace_id = trace_ids[0]

            # Mark this trace as a fixture so the judge uses openai model
            mlflow.flush_trace_async_logging() # ensure all spans are written before the judge reads the trace
            mlflow_client.set_trace_tag(trace_id, "fixture", "true")

            # Queue the judge + promotion check for this trace
            background_tasks.add_task(judge_and_promote_trace, experiment_name, trace_id, bundle.team_id,
                                      prompt_versions_registered, mlflow_client, bundle.sprint_id)
            
            print(f"  trace_id={trace_id}  overall_score={assessment.overall_score}  prompts={prompt_versions_registered}")

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
    use_utf8_streams()
    parser = argparse.ArgumentParser(description="Run one AB-bundle evaluation + judge + promotion cycle")
    parser.add_argument("--model", required=True, help="Ollama model tag to evaluate with")
    parser.add_argument("--experiment-name", default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--baseline", action="store_true",
                        help="Grade with the registered production prompts instead of the prompts in the code")
    args = parser.parse_args()
    asyncio.run(run_fixture_trial(args.model, args.experiment_name, args.repeats, args.baseline))
    
if __name__ == "__main__":
    main()