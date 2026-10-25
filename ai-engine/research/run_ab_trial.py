"""
research/run_ab_trial.py

Manually trigger one full register -> evaluate -> judge -> promote cycle
against the fixed A/B bundles, without going through the FastAPI
endpoint. Reuses evaluate_sprint() and judge_and_promote_trace() unchanged --
this is a thin CLI wrapper, not a parallel reimplementation -- so a promotion
triggered here genuinely exercises the same path the live endpoint uses.

Usage:
    docker compose exec sprintsight_ai python -m research.run_ab_trial --model sprintsight-qwen
"""
import argparse, asyncio, json, mlflow
from pathlib import Path

from schemas.artifact_bundle import ArtifactBundle
from services.evaluator import evaluate_sprint
from judges.promote import judge_and_promote_trace

CS203g6_BUNDLE_PATH = Path(__file__).parent / "cs203g6_AB.json"
CS203jy_BUNDLE_PATH = Path(__file__).parent / "cs203jy_AB.json"
DEFAULT_EXPERIMENT_NAME = "CS203 research 25/10/26"

def load_ab_bundle(ab_bundle_path: Path) -> ArtifactBundle:
    with ab_bundle_path.open() as f:
        return ArtifactBundle.model_validate(json.load(f))

async def run_ab_trial(model_name: str, experiment_name: str = DEFAULT_EXPERIMENT_NAME, repeats: int = 1) -> None:
    mlflow_client = mlflow.MlflowClient()
    for ab_bundle_path in (CS203g6_BUNDLE_PATH, CS203jy_BUNDLE_PATH):
        print(f"Loading A/B bundle from {ab_bundle_path}...")
        bundle = load_ab_bundle(ab_bundle_path)
        for i in range(repeats):
            print(f"[{i + 1}/{repeats}] Evaluating '{model_name}' against {ab_bundle_path.name}...")
            assessment, prompt_versions_registered = await evaluate_sprint(bundle, model_name, experiment_name, mlflow_client)
            trace_id = mlflow.get_last_active_trace_id()
            print(f"  trace_id={trace_id}  overall_score={assessment.overall_score}")

            await asyncio.to_thread(judge_and_promote_trace, experiment_name, trace_id, bundle.team_id, prompt_versions_registered, mlflow_client, bundle.sprint_id)
            print(f"  judging + promotion check complete for trace {trace_id}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Run one AB-bundle evaluation + judge + promotion cycle")
    parser.add_argument("--model", required=True, help="Ollama model tag to evaluate with")
    parser.add_argument("--experiment-name", default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(run_ab_trial(args.model, args.experiment_name, args.repeats))

if __name__ == "__main__":
    main()

#   "sprintsight-llama|llama3.2|Modelfile.llama" \
#   "sprintsight-qwen|qwen3:8b|Modelfile.qwen" \
#   "sprintsight-mistral|mistral:7b|Modelfile.mistral" \
#   "sprintsight-gemma|gemma4:12b|Modelfile.gemma" \
#   "sprintsight-judge-phi|phi4:14b|Modelfile.phi" \
#   "sprintsight-llama31|llama3.1:8b|Modelfile.llama31" \
#   "sprintsight-qwen25-32b|qwen2.5:32b|Modelfile.qwen25-32b" \
#   "sprintsight-r1-32b|deepseek-r1:32b|Modelfile.deepseek-r1" \
#   "sprintsight-coder-32b|qwen2.5-coder:32b|Modelfile.qwen25-coder"