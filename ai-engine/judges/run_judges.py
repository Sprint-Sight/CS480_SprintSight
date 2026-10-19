import os
import time

import mlflow
from dotenv import load_dotenv
from mlflow import MlflowClient
from mlflow.entities import Trace
from mlflow.genai.scorers import scorer
from schemas.cs203_groundtruth import CS203G6_GOLD, CS203JY_GOLD

from judges.citation_ground_custom_judge import (
    JUDGE_MODEL,
    llm_judge_citation_grounding,
)
from judges.code_based_scorer import numeric_grade_accuracy
from judges.trace_adapters import read_candidate
from prompts.dimension_criteria import DIMENSIONS

load_dotenv()  # Load environment variables from .env file

GOLD_BY_TEAM = {
    CS203G6_GOLD.team_id: CS203G6_GOLD,
    CS203JY_GOLD.team_id: CS203JY_GOLD,
}

def _log(msg):
    print(msg, flush=True)

@scorer(name="numeric_grade_accuracy")
def grade_accuracy_from_trace(trace: Trace, expectations: dict):
    rubric, _ = read_candidate(trace) # No bundle: score don't depned on the citation filter
    outputs = {"rubric_scores": {d: (getattr(rubric, d).model_dump() if getattr(rubric, d) else None) for d in DIMENSIONS}}
    return numeric_grade_accuracy.run(outputs=outputs, expectations=expectations)

# Either trace_ids is provided (explicitly select traces) or model/team_id is provided (filter by tags). If both are provided, trace_ids takes precedence.
def select_traces(client: MlflowClient, experiment_id: str, *, trace_ids=None, model=None, team_id=None, max_results=50):
    if trace_ids:
        return [client.get_trace(trace_id) for trace_id in trace_ids]
    clauses = ["trace.status = 'OK'"]
    if model:
        clauses.append(f"tags.model_name = '{model}'")
    if team_id:
        clauses.append(f"tags.team_id = '{team_id}'")
    return list(client.search_traces(
        experiment_ids=[experiment_id], filter_string=" AND ".join(clauses), 
        max_results=max_results, order_by=["start_time DESC"]
    ))

def run_judge_evaluation(experiment_name: str, *, trace_ids=None, model=None, team_id=None, with_judge=True, run_name=None):
    uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(uri)
    _log(f"[1/4] Connecting to MLflow at {uri} (experiment '{experiment_name}')...")
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise SystemExit(f"Experiment '{experiment_name}' not found at {uri}.")
    mlflow.set_experiment(experiment_id=experiment.experiment_id)   # the eval run is created in this experiment
    client = MlflowClient()

    _log("[2/4] Fetching traces...")
    traces = select_traces(client, experiment.experiment_id, trace_ids=trace_ids, model=model, team_id=team_id)
    usable = []
    for i, trace in enumerate(traces, 1):
        team = trace.info.tags.get("team_id")
        gold = GOLD_BY_TEAM.get(team)                       # by the trace's own team_id, never the loop index
        if gold is None:
            _log(f"  [{i}/{len(traces)}] skip {trace.info.trace_id}: no gold for team_id={team!r}")
            continue
        stored = [a for a in (trace.info.assessments or []) if a.name == "gold"]
        if stored and (stored[0].value or {}).get("team_id") == gold.team_id:
            _log(f"  [{i}/{len(traces)}] {trace.info.trace_id} ({team}): gold already correct")
        else:
            for a in stored:                                 # replaces gold stored with the wrong team
                mlflow.delete_assessment(trace_id=trace.info.trace_id, assessment_id=a.assessment_id)
            mlflow.log_expectation(trace_id=trace.info.trace_id, name="gold", value=gold.model_dump(mode="json"))
            _log(f"  [{i}/{len(traces)}] {trace.info.trace_id} ({team}): gold (re)logged")
        usable.append(trace.info.trace_id)
    if not usable:
        raise SystemExit("No judgeable traces selected.")

    traces = [client.get_trace(trace_id) for trace_id in usable]   # re-fetch so logged expectations are included
    scorers = [grade_accuracy_from_trace] + ([llm_judge_citation_grounding] if with_judge else [])
    _log(f"[3/4] Evaluating {len(traces)} trace(s) with {[getattr(s, 'name', s) for s in scorers]} "
         "(the LLM judge takes minutes per trace)...")
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")   # default 10 parallel scorers would swamp one Ollama server
    run_name = run_name or f"judge_{JUDGE_MODEL}_{time.strftime('%Y%m%d-%H%M')}"
    start = time.perf_counter()
    with mlflow.start_run(run_name=run_name):                     # evaluate() reuses the active run
        result = mlflow.genai.evaluate(data=traces, scorers=scorers)
    _log(f"[4/4] Done in {time.perf_counter() - start:.0f}s. Metrics: {result.metrics}")
    return result


if __name__ == "__main__":
    # trace_ids = [ # CS203 research
    #     "tr-7512e4687b4763bc0b5cef70131cd50d", # Mistral JY 2
    #     "tr-289ce911f42c17f44efb1a77b7fc110a", # Mistral JY 1
    #     "tr-f4599f9a485cd50e8e6194768655b072", # Mistral G6 2
    #     "tr-d59741de494cee91812ff7d7b1ee64b0", # Mistral G6 1
    #     "tr-fdb40f993e8a2c17105f14142a751f38", # Gemma JY 2
    #     "tr-98c1757e77871708a73a39f27a32b07f", # Gemma JY 1
    #     "tr-2e6608d1092f8c2c285aefbe4d3c53ad", # Gemma G6 2
    #     "tr-5011c5a6518eda3fd84ff41e908be480", # Gemma G6 1
    #     "tr-4aeb2a23848b6326a4d2beb1b7b6fffc", # Qwen JY 2
    #     "tr-4d562e0ac67755265beee27a40bbdc1b", # Qwen JY 1
    #     "tr-12cab99bef9a264c312d6341ce8b56db", # Qwen G6 2
    #     "tr-14e924bc92b5c0bf680d1d5c112d9dae", # Qwen G6 1
    #     # "tr-1ad2ecf528fd07c80310b279897793db",
    #     # "tr-4eb5815c480602a07cd47b0c6307a4c8"
    # ]
    trace_ids = [ # CS203 research 8/10/26
        "tr-c78e03e428c4662f1edb734ae7db9550", # Mistral JY 
        "tr-c3b3e9e8f38d6ed98f54e8d72efc0fc2", # Mistral G6
        "tr-3132bcc3b6533a7d014fb34c9960c190", # Gemma JY
        "tr-d5c47360ec44c3e451ef81e3a739c9cc", # Gemma G6
        "tr-3f586d55f3d967e3316ee54ac11238dc", # Qwen JY
        "tr-7008be5f51039f720b26bd1fa8250d32", # Qwen G6
    ]
    run_judge_evaluation("CS203 research 8/10/26", model="sprintsight-judge-phi", trace_ids=trace_ids, with_judge=True)