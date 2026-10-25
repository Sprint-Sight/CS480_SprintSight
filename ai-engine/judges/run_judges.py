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

MAX_PENALISED_MAE = 3
MAX_HALLUCINATION = 0.1
MIN_CITATIONS = 10
MIN_GROUNDED_RATE = 0.5

KEEP_ASSESSMENTS = {'gold', 'citation_grounding'} # not produced by the judge

def _log(msg):
    print(msg, flush=True)

@scorer(name="numeric_grade_accuracy")
def grade_accuracy_from_trace(trace: Trace, expectations: dict): # expects the gold rubric to be logged as an expectation on the trace
    rubric, _ = read_candidate(trace) # No bundle: score don't depned on the citation filter
    outputs = {"rubric_scores": {d: (getattr(rubric, d).model_dump() if getattr(rubric, d) else None) for d in DIMENSIONS}}
    return numeric_grade_accuracy.run(outputs=outputs, expectations=expectations)

def find_gold(trace: Trace):
    team, sprint = trace.info.tags.get("team_id"), trace.info.tags.get("sprint_id")
    return GOLD_BY_TEAM.get(team) if sprint else None

# Either trace_ids is provided (explicitly select traces) or model/team_id is provided (filter by tags). If both are provided, trace_ids takes precedence.
def select_traces(client: MlflowClient, experiment_id: str, *, trace_ids=None, model=None, team_id=None, max_results=100):
    if trace_ids:
        return [client.get_trace(trace_id) for trace_id in trace_ids]
    clauses = ["trace.status = 'OK'"]
    if team_id:
        clauses.append(f"tags.team_id = '{team_id}'")
    if model:
        clauses.append(f"tags.model = '{model}'") # the GRADED model
    traces, token = [], None
    while True: # search_traces() returns a page at a time
        page = client.search_traces(experiment_id=[experiment_id], filter=f" AND ".join(clauses), max_results=max_results, order_by=['timestamp_ms DESC'],page_token=token)
        traces.extend(page)
        token = page.token
        if not token or len(traces) >= max_results:
            return traces[:max_results]

def _flag_for_review(result_df: pd.DataFrame, with_judge: bool):
    has_gold = GRADE_COL in result_df.columns # absent when the group had no gold (code-based scorer not run)

    for _, row in result_df.iterrows():
        def val(col):
            v = row.get(col)
            return None if v is None or pd.isna(v) else v

        trace_id, reasons = row["trace_id"], []
        if has_gold:
            mae = val(GRADE_COL)
            if mae is None:
                reasons.append("grade scorer produced no output")
            elif mae > MAX_PENALISED_MAE:
                reasons.append(f"grade_penalised_mae={mae} > {MAX_PENALISED_MAE}")
        if with_judge:
            halluc, count, grounded = val(HALLUCINATION_COL), val(CITATION_COUNT_COL), val(GROUNDED_COL)
            if halluc is None:
                reasons.append("citation judge produced no output") # e.g. the judge call errored
            elif halluc > MAX_HALLUCINATION:
                reasons.append(f"hallucination_rate={halluc} > {MAX_HALLUCINATION}")
            if count is not None and count < MIN_CITATIONS:
                reasons.append(f"citation_count={count} < {MIN_CITATIONS}")
            if grounded is not None and grounded < MIN_GROUNDED_RATE:
                reasons.append(f"grounded_rate={grounded} < {MIN_GROUNDED_RATE}")

        if reasons:
            add_to_review_queue(f"review_queue_{trace_id}", [trace_id])
            _log(f"Trace {trace_id} flagged for review: {', '.join(reasons)}")
        else:
            _log(f"Trace {trace_id} passed all checks.")

def run_judge_evaluation(experiment_name: str, client: MlflowClient, *, trace_ids=None, model=None, team_id=None, with_judge=True, run_name=None) -> list:
    """Returns one evaluate() result per group of traces (gold / no gold). The automatic path judges one trace, so one result."""
    uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(uri)
    _log(f"[1/4] Connecting to MLflow at {uri} (experiment '{experiment_name}')...")
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        raise RuntimeError(f"Experiment '{experiment_name}' not found at {uri}.")
    mlflow.set_experiment(experiment_id=experiment.experiment_id)   # the eval run is created in this experiment

    _log("[2/4] Fetching traces...")
    traces = select_traces(client, experiment.experiment_id, trace_ids=trace_ids, model=model, team_id=team_id)
    with_gold, without_gold = [], [] # code-based scorer only runs for traces whose team's sprint has a gold
    for i, trace in enumerate(traces, 1):
        trace_id, team = trace.info.trace_id, trace.info.tags.get("team_id")
        label = f"  [{i}/{len(traces)}] {trace_id} ({team})"

        for assessment in trace.info.assessments: # clear a previous judge run so results don't pile up
            if assessment.name not in KEEP_ASSESSMENTS:
                mlflow.delete_assessment(trace_id=trace_id, assessment_id=assessment.assessment_id)
                _log(f"{label}: existing assessment '{assessment.name}' deleted")

        gold = find_gold(trace)
        if gold is None:
            _log(f"{label}: no gold for this team/sprint -> LLM judge only")
        else:
            stored = [a for a in (trace.info.assessments or []) if a.name == "gold"]
            logged = (stored[0].value or {}) if stored else {}
            if logged.get("team_id") == gold.team_id and logged.get("sprint_id") == gold.sprint_id:
                _log(f"{label}: gold already correct")
            else: # not logged, or logged for another team/sprint
                for a in stored:
                    mlflow.delete_assessment(trace_id=trace_id, assessment_id=a.assessment_id)
                mlflow.log_expectation(trace_id=trace_id, name="gold", value=gold.model_dump(mode="json"))
                _log(f"{label}: gold (re)logged")

        try: # Fetch the trace again so the logged gold is included in the expectations. If this fails, flag the trace for review.
            fresh = client.get_trace(trace_id)
        except RestException as e:
            _log(f"{label}: failed to fetch trace: {e}")
            add_to_review_queue(f"review_queue_{trace_id}", [trace_id])
            continue
        (with_gold if gold is not None else without_gold).append(fresh)

    if not (with_gold or without_gold):
        raise RuntimeError("No judgeable traces selected.")

    judge = [llm_judge_citation_grounding] if with_judge else []
    groups = [("gold", with_gold, [grade_accuracy_from_trace, *judge]), ("no_gold", without_gold, judge)]
    os.environ.setdefault("MLFLOW_GENAI_EVAL_MAX_WORKERS", "1")   # default 10 parallel scorers would swamp one Ollama server
    base_name = run_name or f"judge_{JUDGE_MODEL}_{time.strftime('%Y%m%d-%H%M')}"
    start, results = time.perf_counter(), []
    for group_name, group, scorers in groups:
        if not group or not scorers:
            continue
        _log(f"[3/4] Evaluating {len(group)} {group_name} trace(s) with {[getattr(s, 'name', s) for s in scorers]} "
             "(the LLM judge takes minutes per trace)...")
        with mlflow.start_run(run_name=f"{base_name}_{group_name}"): # evaluate() reuses the active run
            result = mlflow.genai.evaluate(data=group, scorers=scorers)
        _flag_for_review(result.result_df, with_judge)
        results.append(result)
    _log(f"[4/4] Done in {time.perf_counter() - start:.0f}s. Metrics: {[r.metrics for r in results]}")
    return results

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