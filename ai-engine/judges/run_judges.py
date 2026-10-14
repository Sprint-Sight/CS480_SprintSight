import pandas as pd
import mlflow, os, time
from mlflow import MlflowClient
from mlflow.entities import Trace
from mlflow.genai.scorers import scorer
from mlflow.exceptions import RestException
from judges.code_based_scorer import numeric_grade_accuracy
from judges.citation_ground_custom_judge import llm_judge_citation_grounding, JUDGE_MODEL
from judges.trace_adapters import read_candidate
from schemas.cs203_groundtruth import CS203G6_GOLD, CS203JY_GOLD
from prompts.dimension_criteria import DIMENSIONS
from llmops.review_queue import add_to_review_queue
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

GOLD_BY_TEAM = {
    CS203G6_GOLD.team_id: CS203G6_GOLD,
    CS203JY_GOLD.team_id: CS203JY_GOLD,
}

GRADE_COL = "grade_penalised_mae/value"
MAE_COL = "grade_mae_scored_only/value"
HALLUCINATION_COL = "citation_hallucination_rate/value"
CITATION_COUNT_COL = "citation_count/value"
GROUNDED_COL = "citation_grounded_rate/value"

def _log(msg):
    print(msg, flush=True)

@scorer(name="numeric_grade_accuracy")
def grade_accuracy_from_trace(trace: Trace, expectations: dict): # expects the gold rubric to be logged as an expectation on the trace
    rubric, _ = read_candidate(trace) # No bundle: score don't depned on the citation filter
    outputs = {"rubric_scores": {d: (getattr(rubric, d).model_dump() if getattr(rubric, d) else None) for d in DIMENSIONS}}
    return numeric_grade_accuracy.run(outputs=outputs, expectations=expectations)

# Either trace_ids is provided (explicitly select traces) or model/team_id is provided (filter by tags). If both are provided, trace_ids takes precedence.
def select_traces(client: MlflowClient, experiment_id: str, *, trace_ids=None, model=None, team_id=None, max_results=100):
    if trace_ids:
        return [client.get_trace(trace_id) for trace_id in trace_ids]
    if not model and not team_id:
        clauses = ["trace.status = 'OK'"]
        traces, token = [], None
        while True: # Fetch traces in pages until we have enough or there are no more
            page = client.search_traces( # search_traces() returns a page of traces, not all at once
                locations=[experiment_id], filter_string=" AND ".join(clauses), 
                max_results=max_results, order_by=["timestamp_ms DESC"], page_token=token
            )
            traces.extend(page)
            token = page.token
            if not token or len(traces) >= max_results:
                break

        return traces

def _flag_for_review(result_df: pd.DataFrame, with_judge: bool):

    USED_COLS = [GRADE_COL, COVERGAE_COL := "coverage_check/value"]
    JUDGE_COLS = [HALLUCINATION_COL, CITATION_COUNT_COL, GROUNDED_COL]

    needed = USED_COLS + (JUDGE_COLS if with_judge else [])
    
    for _, row in result_df.iterrows():
        trace_id = row["trace_id"]
        mae, cov = row[GRADE_COL], row[COVERGAE_COL]
        halluc, count, ground = row[HALLUCINATION_COL], row[CITATION_COUNT_COL], row[GROUNDED_COL]
        reason = ""
        if pd.isna(mae) or pd.isna(cov):  # a scorer failed (e.g. judge call errored)
            reason = "Missing scorer output: " + ", ".join(f"{c}={row[c]}" for c in needed if pd.isna(row[c]))
        if mae > 3:
            reason += f"grade={mae}, hallucination_rate={halluc}, citation_count={count}, "
        if (with_judge and halluc > 0.1):
            reason += f"hallucination_rate={halluc} > 0.1, "
        if (with_judge and count < 10):
            reason += f"citation_count={count} < 10, "
        if (with_judge and ground < 0.5):
            reason += f"grounded_rate={ground} < 0.83, "

        if reason:
            add_to_review_queue(f"review_queue_{trace_id}", [trace_id])
            _log(f"Trace {trace_id} flagged for review: {reason.strip(', ')}")
        else:
            _log(f"Trace {trace_id} passed all checks: grade={mae}, hallucination_rate={halluc}, citation_count={count}, grounded_rate={ground}")

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
    #traces = select_traces(client, experiment.experiment_id, trace_ids=trace_ids, model=model, team_id=team_id)
    traces, usable = select_traces(client, experiment.experiment_id), [] # traces that have gold logged for their team and are ready to be evaluated
    for i, trace in enumerate(traces, 1):
        team = trace.info.tags.get("team_id")

        # Delete existing assessment for this trace
        for assessment in trace.info.assessments:
            if assessment.name != "gold": 
                mlflow.delete_assessment(trace_id=trace.info.trace_id, assessment_id=assessment.assessment_id)
                _log(f"  [{i}/{len(traces)}] {trace.info.trace_id} ({team}): existing assessment deleted")

        # Get the gold rubric for this trace's team and log it if not already logged
        gold = GOLD_BY_TEAM.get(team) # by the trace's own team_id, never the loop index
        if gold is None: # no gold for this team, skip it
            _log(f"  [{i}/{len(traces)}] skip {trace.info.trace_id}: no gold for team_id={team!r}")
            continue
        stored = [a for a in (trace.info.assessments or []) if a.name == "gold"] # gold already logged for this trace
        if stored and (stored[0].value or {}).get("team_id") == gold.team_id: # gold already logged for this team, skip it
            _log(f"  [{i}/{len(traces)}] {trace.info.trace_id} ({team}): gold already correct")
        else: # gold not logged or logged for the wrong team, log it now
            for a in stored: # replaces gold stored with the wrong team
                mlflow.delete_assessment(trace_id=trace.info.trace_id, assessment_id=a.assessment_id)
            mlflow.log_expectation(trace_id=trace.info.trace_id, name="gold", value=gold.model_dump(mode="json"))
            _log(f"  [{i}/{len(traces)}] {trace.info.trace_id} ({team}): gold (re)logged")
        
        try: # Fetch the trace again to ensure the logged gold is included in the expectations for evaluation. If this fails, flag the trace for review.
            usable.append(client.get_trace(trace.info.trace_id))   # re-fetch so logged expectations are included
        except RestException as e:
            _log(f"  [{i}/{len(traces)}] {trace.info.trace_id}: failed to fetch trace: {e}")
            add_to_review_queue(f"review_queue_{trace.info.trace_id}", [trace.info.trace_id]) # flag for review if we can't fetch it

    if not usable:
        raise SystemExit("No judgeable traces selected.")

    scorers = [grade_accuracy_from_trace] + ([llm_judge_citation_grounding] if with_judge else [])
    _log(f"[3/4] Evaluating {len(usable)} trace(s) with {[getattr(s, 'name', s) for s in scorers]} "
         "(the LLM judge takes minutes per trace)...")
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")   # default 10 parallel scorers would swamp one Ollama server
    run_name = run_name or f"judge_{JUDGE_MODEL}_{time.strftime('%Y%m%d-%H%M')}"
    start = time.perf_counter()
    with mlflow.start_run(run_name=run_name): # evaluate() reuses the active run
        result = mlflow.genai.evaluate(data=usable, scorers=scorers)

    _flag_for_review(result.result_df, with_judge)
    _log(f"[4/4] Done in {time.perf_counter() - start:.0f}s. Metrics: {result.metrics}")
    return result

if __name__ == "__main__":
    trace_ids = [ # CS203 research 12/10/26
        #"tr-6ecacfe8b7be2855f93d91f02fd4bfb9", # Gemma JY
        "tr-10525918449401e0b9c0c7f043efed4f", # Gemma G6
        "tr-2e7b0a535108049742555b098d902588", # Qwen JY
        #"tr-7fea697f539e3d43e6f4f6b734f7377d", # Qwen G6
    ]
    trace_ids = [ # CS203 research 12/10/26
        "tr-a81b348e7deb980a215d8040d2179f59", # Gemma JY
        #"tr-2bc45c19f5b1b546fc8e2ca487dfea8a", # Gemma G6
        "tr-a9d0be7395c559d5297c40363a201dae", # Qwen JY
        "tr-af621323798aa24eb3f2fb61ffc0bbd2", # Qwen G6
    ]
    #run_judge_evaluation("CS203 research 13/10/26", model="sprintsight-judge-phi", trace_ids=trace_ids, with_judge=True)
    run_judge_evaluation("CS203 research 14/10/26", model="sprintsight-judge-phi", team_id='cs203g6', with_judge=True)