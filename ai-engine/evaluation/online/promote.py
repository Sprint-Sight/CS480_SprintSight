import json
import logging
import threading

import mlflow
import pandas as pd
from llmops.prompt_registry import (
    PRODUCTION_ALIAS,
    assign_prompt_alias,
    get_production_prompt,
)
from mlflow import MlflowClient, MlflowException
from prompts.dimension_criteria import DIMENSIONS
from schemas.failure_class import is_transient

from evaluation.judges.flagging import (
    JUDGE_FAILURE_CLASS_COL,
    MAX_SEVERITY_WEIGHTED_RATE,
)
from evaluation.online.run_judges import run_judge_evaluation
from evaluation.stats import paired_bootstrap_diff

JUDGE_RESULTS_TAG = "judge_results"       # JSON on each prompt version: {"team|sprint|model": {"abs_error": x, "hallucination": y, "severity_weighted": z, "citation_count": n}}
PROMOTION_MAE_THRESHOLD = 2.0             # absolute gate: never promote a prompt whose per-dimension error is above this
PROMOTION_HALLUCINATION_THRESHOLD = 0.1   # absolute gate on citation hallucination rate
PROMOTION_SEVERITY_WEIGHTED_THRESHOLD = MAX_SEVERITY_WEIGHTED_RATE  # absolute gate on the severity-weighted rate: same bar as flagging
MIN_SHARED_INPUTS = 3                     # challenger and production must both have results on this many team|sprint|model inputs (paired_bootstrap_diff needs 3)
MIN_IMPROVEMENT = 0.2                     # mean abs_error must drop by at least this AND the bootstrap CI must exclude 0
MIN_CITATIONS_FOR_PROMOTION = 3           # judged citations of THIS dimension on the trace, not the trace overall
HALLUCINATION_TOLERANCE = 0.02            # challenger may not exceed production by more than this on any shared input
SEVERITY_TOLERANCE = 0.03                 # same, for the severity-weighted rate

log = logging.getLogger("sprintsight.judges.promote")
_JUDGE_LOCK = threading.Lock()  # one judge + promotion at a time: one shared Ollama, and alias flips must not race

_input_key = lambda team_id, sprint_id, model, judge_model: f"{team_id}|{sprint_id}|{model}|{judge_model}"

class JudgeTransientFailure(RuntimeError):
    """The judge call failed for a reason that may pass (see schemas.failure_class)."""


def judge_transient_failures(results) -> set[str]:
    """Transient failure classes recorded by the judge scorer across `results`."""
    found: set[str] = set()
    for result in results:
        frame = getattr(result, "result_df", None)
        if frame is None or JUDGE_FAILURE_CLASS_COL not in frame.columns:
            continue
        found |= {str(value) for value in frame[JUDGE_FAILURE_CLASS_COL].dropna() if is_transient(value)}
    return found


def run_judge_and_promotion(experiment_name: str, trace_id: str, team_id: str, prompt_versions_registered: dict, client: MlflowClient, sprint_id: str | None = None):
    """Judge one trace, then evaluate prompt promotion. RAISES if judging fails, so the durable
    job queue (evaluation/online/scheduler.py) can retry it; a failure while deciding promotion is only
    logged, because re-running a minutes-long judge would not change that decision."""
    if not trace_id:
        return
    with _JUDGE_LOCK:
        mlflow.flush_trace_async_logging() # ensure all spans are written before the judge reads the trace
        failed = _failed_dimensions(client.get_trace(trace_id))
        if len(failed) == len(DIMENSIONS):
            log.info("All dimensions failed for trace %s; skipping judge + promotion.", trace_id)
            return
        results = run_judge_evaluation(experiment_name, client, trace_ids=[trace_id], team_id=team_id, with_judge=True, run_name=f"judge_{trace_id}")
        # MLflow swallows a scorer's error, so "the judge ran" does not mean "the judge worked".
        # A transient failure (Ollama down, timeout) is worth another attempt from the queue; a
        # permanent one (the prompt cannot fit) is not, and has already been flagged for review.
        transient = judge_transient_failures(results)
        if transient:
            raise JudgeTransientFailure(f"judge failed for trace {trace_id}: {', '.join(sorted(transient))}")
        for result in results:
            try:
                _determine_promotion(result, trace_id, team_id, sprint_id, prompt_versions_registered, client, failed)
            except Exception:
                log.exception("Failed to determine promotion for trace %s", trace_id)

def judge_and_promote_trace(experiment_name: str, trace_id: str, team_id: str, prompt_versions_registered: dict, client: MlflowClient, sprint_id: str | None = None):
    """Fire-and-forget form kept for the research trial scripts (they pass it to their own
    BackgroundTasks). The API uses the durable queue and run_judge_and_promotion instead."""
    try:
        run_judge_and_promotion(experiment_name, trace_id, team_id, prompt_versions_registered, client, sprint_id)
    except Exception:
        log.exception("Failed to run judge evaluation for trace %s", trace_id)

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
    """What the judge run says about ONE dimension's prompt. Citation metrics come only from
    that dimension's own citations. They used to fall back to the trace-wide rate and count, so
    a dimension that cited nothing was credited with its neighbours' evidence and could be
    promoted on it; now it simply has no citation scores and cannot pass the gates."""
    found = {"abs_error": metrics.get(f"grade_abs_error_{dimension}/mean"), # absent when the trace had no gold
             "hallucination": metrics.get(f"citation_hallucination_rate_{dimension}/mean"),
             "severity_weighted": metrics.get(f"citation_severity_weighted_rate_{dimension}/mean"),
             "citation_count": metrics.get(f"citation_count_{dimension}/mean")}
    return {n: float(v) for n, v in found.items() if v is not None}

def _passes_criteria(scores: dict) -> bool:
    if scores.get("abs_error") is not None and scores["abs_error"] > PROMOTION_MAE_THRESHOLD:
        return False
    # Every citation rule is about this dimension's own evidence, and every one must be present:
    # no judged citations (or no judge result) -> no promotion.
    if scores.get("citation_count", 0) < MIN_CITATIONS_FOR_PROMOTION:
        return False
    halluc, severity = scores.get("hallucination"), scores.get("severity_weighted")
    return halluc is not None and severity is not None \
           and halluc <= PROMOTION_HALLUCINATION_THRESHOLD \
           and severity <= PROMOTION_SEVERITY_WEIGHTED_THRESHOLD

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

def _worse(c: dict, p: dict, metric: str, tolerance: float) -> bool:
    return metric in c and metric in p and c[metric] > p[metric] + tolerance

def _compare(challenger, production):
    """Does the challenger beat production? Both are judged on the inputs they share. A mean
    gain over two or three inputs says nothing about how much of it is luck, so the decision
    uses the paired-bootstrap CI of the error difference (evaluation.offline.analysis): the gain
    must be at least MIN_IMPROVEMENT *and* the CI must exclude 0."""
    c, p = _load_results(challenger), _load_results(production)
    shared = sorted(c.keys() & p.keys())
    if len(shared) < MIN_SHARED_INPUTS:
        return "insufficient", {"shared_inputs": len(shared), "needed": MIN_SHARED_INPUTS}
    paired = [k for k in shared if "abs_error" in c[k] and "abs_error" in p[k]]
    if len(paired) < MIN_SHARED_INPUTS:
        return "insufficient", {"shared_inputs": len(shared), "inputs_with_abs_error_on_both": len(paired),
                                "needed": MIN_SHARED_INPUTS}
    frame = pd.DataFrame(
        [{"example_id": k, "model": "production", "abs_error": p[k]["abs_error"]} for k in paired]
        + [{"example_id": k, "model": "challenger", "abs_error": c[k]["abs_error"]} for k in paired]
    )
    diff = paired_bootstrap_diff(frame, "abs_error", "production", "challenger")  # mean(production - challenger): positive = challenger better
    if diff is None:
        return "insufficient", {"shared_inputs": len(shared), "reason": "too few paired observations"}
    regressed = [k for k in shared if _worse(c[k], p[k], "hallucination", HALLUCINATION_TOLERANCE)
                 or _worse(c[k], p[k], "severity_weighted", SEVERITY_TOLERANCE)]
    detail = {"shared_inputs": len(shared), "paired_inputs": diff.n,
              "mean_abs_error_gain": round(diff.mean_diff, 3),
              "ci95": [round(diff.ci_low, 3), round(diff.ci_high, 3)],
              "citation_regressions": regressed}
    improved = diff.mean_diff >= MIN_IMPROVEMENT and diff.ci_low > 0
    return ("promote" if improved and not regressed else "keep"), detail

def _promote(name: str, version, reason: str):
    assign_prompt_alias(name, PRODUCTION_ALIAS, version)
    log.info("Promoted '%s' version %s to production: %s", name, version, reason)
    print(f"Promoted '{name}' version {version} to production: {reason}")

def _failed_dimensions(trace) -> set[str]:
    root = next((s for s in trace.data.spans if s.parent_id is None), None)
    outputs = root.outputs if root is not None and isinstance(root.outputs, dict) else {}
    return set(outputs.get('failed_dimensions') or [])