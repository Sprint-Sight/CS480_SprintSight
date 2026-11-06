import json, logging, threading, mlflow
from statistics import mean
from mlflow import MlflowClient, MlflowException
from prompts.dimension_criteria import DIMENSIONS
from judges.run_judges import run_judge_evaluation
from llmops.prompt_registry import PRODUCTION_ALIAS, get_production_prompt, assign_prompt_alias

JUDGE_RESULTS_TAG = "judge_results"       # JSON on each prompt version: {"team|sprint|model": {"abs_error": x, "hallucination": y}}
PROMOTION_MAE_THRESHOLD = 2.0             # absolute gate: never promote a prompt whose per-dimension error is above this
PROMOTION_HALLUCINATION_THRESHOLD = 0.1   # absolute gate on citation hallucination rate
MIN_SHARED_INPUTS = 2                     # challenger and production must both have results on this many team|sprint|model inputs
MIN_IMPROVEMENT = 0.2                     # mean abs_error must drop by at least this
MIN_CITATIONS_FOR_PROMOTION = 3
HALLUCINATION_TOLERANCE = 0.02            # challenger may not exceed production by more than this on any shared input
HALLUCINATION_KEY = "citation_hallucination_rate/mean"

log = logging.getLogger("sprintsight.judges.promote")
_JUDGE_LOCK = threading.Lock()  # one judge + promotion at a time: one shared Ollama, and alias flips must not race

_input_key = lambda team_id, sprint_id, model, judge_model: f"{team_id}|{sprint_id}|{model}|{judge_model}"

def judge_and_promote_trace(experiment_name: str, trace_id: str, team_id: str, prompt_versions_registered: dict, client: MlflowClient, sprint_id: str | None = None):
    if not trace_id:
        return
    with _JUDGE_LOCK:
        try:
            mlflow.flush_trace_async_logging() # ensure all spans are written before the judge reads the trace
            failed = _failed_dimensions(client.get_trace(trace_id))
            if len(failed) == len(DIMENSIONS):
                log.info("ALl dimensions failed for trace %s; skipping judge + promotion.", trace_id)
                return
            results = run_judge_evaluation(experiment_name, client, trace_ids=[trace_id], team_id=team_id, with_judge=True, run_name=f"judge_{trace_id}")
        except Exception:
            log.exception("Failed to run judge evaluation for trace %s", trace_id)
            return
        for result in results:
            try:
                _determine_promotion(result, trace_id, team_id, sprint_id, prompt_versions_registered, client, failed)
            except Exception:
                log.exception("Failed to determine promotion for trace %s", trace_id)

def _determine_promotion(judge_result, trace_id, team_id, sprint_id, prompt_versions_registered: dict, client: MlflowClient, failed=frozenset()):
    trace = client.get_trace(trace_id)
    key = _input_key(team_id, sprint_id, trace.info.tags.get("model", "unknown_model"), trace.info.tags.get("judge_model", "unknown_judge_model"))
    for dimension in DIMENSIONS:
        if dimension in failed:
            continue  # this dimension failed in the trace; judge did not run on it
        name = f"Evaluate_{dimension}"
        version = prompt_versions_registered.get(name)
        if version is None:
            continue
        scores = _dimension_scores(judge_result.metrics, dimension)
        if not scores:
            log.info("No judge scores for '%s'; leaving its aliases unchanged.", name)
            continue

        _record_result(client, name, version, key, scores, trace_id)  # always store: it is the baseline later challengers are compared with
        if not _passes_criteria(scores):
            log.info("'%s' v%s fails the absolute gates %s; not promoting.", name, version, scores)
            continue

        production = get_production_prompt(name)
        if production is None:
            _promote(name, version, "there is no production prompt for this dimension")
            continue
        if int(production.version) == int(version):
            continue  # this run graded with production itself; baseline recorded above

        verdict, detail = _compare(client.get_prompt_version(name, str(version)),
                                   client.get_prompt_version(name, str(production.version)))
        if verdict == "promote":
            _promote(name, version, f"beats production v{production.version}: {detail}")
        else:
            log.info("Keeping production for '%s' v%s (%s): %s", name, production.version, verdict, detail)

def _dimension_scores(metrics: dict, dimension: str) -> dict:
    found = {"abs_error": metrics.get(f"grade_abs_error_{dimension}/mean"), # absent when the trace had no gold
             "hallucination": metrics.get(f"citation_hallucination_rate_{dimension}/mean", metrics.get(HALLUCINATION_KEY)),
             "citation_count": metrics.get(f"citation_count/mean")}
    return {n: float(v) for n, v in found.items() if v is not None}

def _passes_criteria(scores: dict) -> bool:
    if scores.get("abs_error") is not None and scores["abs_error"] > PROMOTION_MAE_THRESHOLD:
        return False
    halluc = scores.get("hallucination") # must exist: no judge result -> no promotion
    return halluc is not None and halluc <= PROMOTION_HALLUCINATION_THRESHOLD \
           and scores.get("citation_count", 0) >= MIN_CITATIONS_FOR_PROMOTION

def _load_results(prompt_version) -> dict:
    try:
        return json.loads((prompt_version.tags or {}).get(JUDGE_RESULTS_TAG, "{}"))
    except json.JSONDecodeError:
        return {}

def _merge_sample(entry: dict, scores: dict, trace_id: str) -> dict:
    counts = entry.setdefault("n", {})
    for metric, value in scores.items():
        n = counts.get(metric, 0)
        entry[metric] = round((entry.get(metric, 0.0) * n + value) / (n + 1), 6)   # running mean
        counts[metric] = n + 1
    entry.setdefault("trace_ids", []).append(trace_id)
    return entry

def _record_result(client: MlflowClient, name, version, key, scores, trace_id):
    try:
        results = _load_results(client.get_prompt_version(name, str(version)))
        entry = results.get(key, {})
        if trace_id in entry.get("trace_ids", []):
            return                                    # this trace is already counted; re-judging must not count it twice
        results[key] = _merge_sample(entry, scores, trace_id)
        client.set_prompt_version_tag(name, str(version), JUDGE_RESULTS_TAG, json.dumps(results))
    except MlflowException:
        log.exception("Could not record %s on '%s' v%s", scores, name, version)

def _compare(challenger, production):
    c, p = _load_results(challenger), _load_results(production)
    shared = sorted(c.keys() & p.keys())
    if len(shared) < MIN_SHARED_INPUTS:
        return "insufficient", {"shared_inputs": len(shared), "needed": MIN_SHARED_INPUTS}
    gains = [p[k]["abs_error"] - c[k]["abs_error"] for k in shared if "abs_error" in c[k] and "abs_error" in p[k]]  # positive = challenger better
    if not gains:
        return "insufficient", {"shared_inputs": len(shared), "reason": "no abs_error on both"}
    gain = mean(gains)
    regressed = [k for k in shared if "hallucination" in c[k] and "hallucination" in p[k]
                 and c[k]["hallucination"] > p[k]["hallucination"] + HALLUCINATION_TOLERANCE]
    detail = {"shared_inputs": len(shared), "mean_abs_error_gain": round(gain, 3), "hallucination_regressions": regressed}
    return ("promote" if gain >= MIN_IMPROVEMENT and not regressed else "keep"), detail

def _promote(name: str, version, reason: str):
    assign_prompt_alias(name, PRODUCTION_ALIAS, version)
    log.info("Promoted '%s' version %s to production: %s", name, version, reason)
    print(f"Promoted '{name}' version {version} to production: {reason}")

def _failed_dimensions(trace) -> set[str]:
    root = next((s for s in trace.data.spans if s.parent_id is None), None)
    outputs = root.outputs if root is not None and isinstance(root.outputs, dict) else {}
    return set(outputs.get('failed_dimensions') or [])