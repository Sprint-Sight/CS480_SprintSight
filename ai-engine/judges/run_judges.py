import os
import time

import mlflow
import pandas as pd
from dotenv import load_dotenv
from mlflow import MlflowClient
from mlflow.entities import AssessmentSourceType, Trace
from mlflow.exceptions import RestException
from mlflow.genai.scorers import scorer

from evaluation.benchmarks import online_gold
from judges.citation_ground_custom_judge import (
    JUDGE_MODEL,
    llm_judge_citation_grounding,
)
from judges.code_based_scorer import numeric_grade_accuracy
from judges.flagging import (
    GRADE_COL,
    evaluate_flags,
    production_reasons,
    research_reasons,
)
from judges.trace_adapters import read_candidate
from llmops.review_queue import add_to_review_queue
from prompts.dimension_criteria import DIMENSIONS
from services.save_results import save_judge_results

load_dotenv()  # Load environment variables from .env file

# Flagging rules, thresholds and result-frame column names live in judges/flagging.py.
# Research-only reasons (comparison against a gold assessment) are kept apart from production
# reasons there; only production reasons go to the review queue unless explicitly opted in.
QUEUE_RESEARCH_FLAGS = os.getenv("JUDGE_QUEUE_RESEARCH_FLAGS", "0").strip().lower() in {"1", "true", "yes"}

KEEP_ASSESSMENTS = {'gold'} # not produced by the judge

ALL_GOLD = online_gold() # All available golds (synthetic_v2 + cs203), keyed by lower-cased team_id

def _log(msg):
    print(msg, flush=True)

@scorer(name="numeric_grade_accuracy")
def grade_accuracy_from_trace(trace: Trace, expectations: dict): # expects the gold rubric to be logged as an expectation on the trace
    rubric, _ = read_candidate(trace) # No bundle: score don't depned on the citation filter
    outputs = {"rubric_scores": {d: (getattr(rubric, d).model_dump() if getattr(rubric, d) else None) for d in DIMENSIONS}}
    return numeric_grade_accuracy.run(outputs=outputs, expectations=expectations)

def _root_outputs(trace: Trace) -> dict:
    root = next((s for s in trace.data.spans if s.parent_id is None), None)
    out = root.outputs if root is not None else None
    return out if isinstance(out, dict) else {}

def _sprint_of(trace: Trace) -> str | None: # trace tag first, then the root span's output
    return trace.info.tags.get("sprint_id") or _root_outputs(trace).get("sprint_id")

def _team_of(trace: Trace) -> str | None: # trace tag first, then the root span's output; lowercased to match GOLD_BY_TEAM
    team = trace.info.tags.get("team_id") or _root_outputs(trace).get("team_id")
    return team.strip().lower() if isinstance(team, str) else None

# Gold for this trace's team AND sprint, or None -> only the LLM judge applies
def find_gold(trace: Trace):
    gold = ALL_GOLD.get(_team_of(trace))
    if gold is None:
        return None
    sprint = _sprint_of(trace)
    if sprint is not None and sprint != gold.sprint_id: # store gold for team/sprint only if the trace's sprint matches the gold's sprint; otherwise, skip the gold and let the LLM judge handle it
        _log(f"  {trace.info.trace_id}: sprint '{sprint}' != gold sprint '{gold.sprint_id}' -> gold skipped")
    return gold

# Either trace_ids is provided (explicitly select traces) or model/team_id is provided (filter by tags). If both are provided, trace_ids takes precedence.
def select_traces(client, experiment_id, *, trace_ids=None, model=None, team_id=None, max_results=100):
    if trace_ids:
        found = []
        for tid in trace_ids:
            try:
                found.append(client.get_trace(tid))
            except RestException as e:          # e.g. "not fully exported yet"
                _log(f"  skip {tid}: {e}")
        return found
    clauses = ["trace.status = 'OK'"]
    if team_id:
        clauses.append(f"tags.team_id = '{team_id}'")
    if model:
        clauses.append(f"tags.model = '{model}'")
    traces, token = [], None
    while True:
        page = client.search_traces(locations=[experiment_id], filter_string=" AND ".join(clauses),
                                    max_results=100, order_by=["timestamp_ms DESC"], page_token=token)
        traces.extend(t for t in page if "judge_model" not in t.info.tags)   # judge traces carry candidate tags
        token = page.token
        if not token or len(traces) >= max_results:
            return traces[:max_results]

def _flag_for_review(result_df: pd.DataFrame, with_judge: bool):
    has_gold = GRADE_COL in result_df.columns # absent when the group had no gold (code-based scorer not run)

    for _, row in result_df.iterrows():
        trace_id = row["trace_id"]
        reasons = evaluate_flags(row.to_dict(), has_gold=has_gold, with_judge=with_judge)
        production, research = production_reasons(reasons), research_reasons(reasons)

        if research:
            _log(f"Trace {trace_id} research flags (not queued): {', '.join(r.message for r in research)}")
        if production or (research and QUEUE_RESEARCH_FLAGS):
            queued = production + (research if QUEUE_RESEARCH_FLAGS else [])
            add_to_review_queue(f"review_queue_{trace_id}", [trace_id])
            _log(f"Trace {trace_id} flagged for review: {', '.join(r.message for r in queued)}")
        elif not research:
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
            if assessment.name not in KEEP_ASSESSMENTS and assessment.source.source_type != AssessmentSourceType.HUMAN: # instructor labels survive a re-judge
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
        if gold is not None and not any(a.name == "gold" for a in (fresh.info.assessments or [])):
            _log(f"{label}: gold not visible after logging -> LLM judge only") # avoids a silent scorer failure
            gold = None
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
        
        with mlflow.start_run(run_name=f"{base_name}_{group_name}") as run: # evaluate() reuses the active run
            result = mlflow.genai.evaluate(data=group, scorers=scorers)
            if result.result_df is not None:
                save_judge_results(
                    experiment_name=experiment_name,
                    judge_model=JUDGE_MODEL,
                    group_name=group_name,
                    run_id=run.info.run_id,
                    result_df=result.result_df,
                    trace_meta={t.info.trace_id: {"team_id": _team_of(t), 
                                                  "sprint_id": _sprint_of(t), 
                                                  "model": t.info.tags.get("model")} for t in group}
                )

        if result.result_df is None:
            raise RuntimeError("evaluate() returned no result; df; cannot flag traces for review.")
        
        _flag_for_review(result.result_df, with_judge) # Flag traces for review if they fail any of the checks (MAE, hallucination, grounded rate, etc.)
        results.append(result)

    _log(f"[4/4] Done in {time.perf_counter() - start:.0f}s. Metrics: {[r.metrics for r in results]}")
    return results

### Uncomment if you want to run judge only for specific traces you want to test
# if __name__ == "__main__":
    ### CHANGE ME: change trace_ids with traces you want to test
#     trace_ids = [ # CS203 research 12/10/26
#         #"tr-6ecacfe8b7be2855f93d91f02fd4bfb9", # Gemma JY
#         "tr-10525918449401e0b9c0c7f043efed4f", # Gemma G6
#         "tr-2e7b0a535108049742555b098d902588", # Qwen JY
#         #"tr-7fea697f539e3d43e6f4f6b734f7377d", # Qwen G6
#     ]
#     trace_ids = [ # CS203 research 12/10/26
#         "tr-a81b348e7deb980a215d8040d2179f59", # Gemma JY
#         #"tr-2bc45c19f5b1b546fc8e2ca487dfea8a", # Gemma G6
#         "tr-a9d0be7395c559d5297c40363a201dae", # Qwen JY
#         "tr-af621323798aa24eb3f2fb61ffc0bbd2", # Qwen G6
#     ]
#     #run_judge_evaluation("CS203 research 13/10/26", model="sprintsight-judge-phi", trace_ids=trace_ids, with_judge=True)
#     run_judge_evaluation("CS203 research 14/10/26", model="sprintsight-judge-phi", team_id='cs203g6', with_judge=True)