import logging, threading
from mlflow import MlflowClient, MlflowException
from schemas.rubrics_dimension_score import DimensionName
from prompts.dimension_criteria import DIMENSIONS
from judges.run_judges import run_judge_evaluation
from llmops.prompt_registry import PRODUCTION_ALIAS, get_production_prompt, assign_prompt_alias

'''
Call judge on given experiment trace_id that just ran
Promote challenger prompts to production if they meet criteria for promotion
'''

PROMOTION_MAE_THRESHOLD = 2.0 # If challenger prompt's MAE is within this threshold of the production prompt's MAE, promote it
PROMOTION_HALLUCINATION_THRESHOLD = 0.1 # If challenger prompt's hallucination rate is within this threshold of the production prompt's hallucination rate, promote it
HALLUCINATION_KEY = 'citation_hallucination_rate/mean'
_JUDGE_LOCK = threading.Lock()

log = logging.getLogger('springsight.judges.promote')

# Run judge on given trace, then promote challenger prompts to production if they meet criteria for promotion
def judge_and_promote_trace(experiment_name: str, trace_id: str, team_id: str, prompt_versions_registered: dict, client: MlflowClient, sprint_id: str | None = None):
    if not trace_id:
        return 
    with _JUDGE_LOCK: # Ensure only one judge runs at a time to avoid race conditions in prompt promotion
        try:
            results = run_judge_evaluation(experiment_name, client, trace_ids=[trace_id], team_id=team_id, with_judge=True, run_name=f"judge_{trace_id}")
        except Exception as e:
            log.exception(f"Failed to run judge evaluation for trace {trace_id}: {e}")
            return
        for result in results:
            _determine_promotion(result, trace_id, team_id, sprint_id, prompt_versions_registered, client)

# Promote prompts that were just registered in the given trace if they meet the promotion criteria
def _determine_promotion(judge_result, trace_id, team_id, sprint_id, prompt_versions_registered: dict, client: MlflowClient):
    trace = client.get_trace(trace_id)
    mae = judge_result.metrics.get('grade_penalised_mae/mean')
    hallucination_rate = judge_result.metrics.get('llm_judge-citation_grounding/citation_hallucination_rate/mean')

    # 1st check: if current challenger prompt does not meet promotion criteria, don't promote it
    if mae is None or mae > PROMOTION_MAE_THRESHOLD:
        return
    if hallucination_rate is not None and hallucination_rate > PROMOTION_HALLUCINATION_THRESHOLD:
        return

    # 2nd check: if current challenger prompt meets promotion criteria, check if it's better than the production prompt
    # Check if there is trace with same prompt name with alias 'production' and compare the metrics. 
    # If the challenger prompt is better or if there is currently no prodcution prompt, promote it.
    for dimension in DIMENSIONS:
        prompt_name = f"Evaluate_{dimension}"
        production_prompt = get_production_prompt(prompt_name)

        # Currently, if there is no production prompt for this dimension, we promote the challenger prompt.
        if not production_prompt: # If there is no production prompt for this dimension, promote the challenger prompt
            prompt_version = prompt_versions_registered.get(prompt_name)
            if prompt_version:
                _promote(prompt_name, prompt_version, f"Challenger is better than production for trace {trace_id}.")
                continue

        # Get production prompt's metrics from the trace and compare with challenger prompt's metrics
        scores = _dimension_scores(judge_result.metrics, dimension)
        if not scores:
            log.info("No judge scores for '%s'; leaving its aliases unchanged.", prompt_name)
            continue

        # Record this version's result for this team+sprint. It is the baseline later challengers are compared with.
        for metric, value in scores.items():
            try:
                client.set_prompt_version_tag(prompt_name, prompt_version, f"judge.{metric}", str(value))
            except MlflowException:
                log.exception("Could not record %s=%s on '%s' v%s", metric, value, prompt_name, prompt_version)

        production = get_production_prompt(prompt_name)
        if production is not None and int(production.version) == int(prompt_version):
            continue # this run graded with production itself; baseline recorded above
        if not _passes_criteria(scores):
            log.info("'%s' v%s fails the absolute gates %s; not promoting.", prompt_name, prompt_version, scores)
            continue
        if production is None:
            _promote(prompt_name, prompt_version, "there is no production prompt for this dimension")
            continue

        # Challenger vs production on the SAME team + sprint, over the metrics both have.
        baseline = {m: float(production.tags[f"judge.{m}"]) for m in scores if f"judge.{m}" in production.tags}
        if not baseline:
            log.info("Production '%s' v%s has no recorded result; keeping it. Challenger result stored.",
                     prompt_name, production.version)
            continue
        no_worse = all(scores[m] <= baseline[m] for m in baseline)
        better = any(scores[m] < baseline[m] for m in baseline)
        if no_worse and better:
            _promote(prompt_name, prompt_version, f"challenger {scores} beats production v{production.version} {baseline}")
        else:
            log.info("Keeping production for '%s': challenger %s vs production %s.", prompt_name, scores, baseline)

            # Current challenger prompts are better than production prompts, so promote them
            _promote(prompt_name, prompt_versions_registered.get(prompt_name), f"Challenger is better than production for trace {trace_id}.")

def _promote(name: str, version, reason: str):
    assign_prompt_alias(name, PRODUCTION_ALIAS, version)
    log.info(f"Promoted prompt '{name}' version {version} to production: {reason}")
    print(f"Promoted prompt '{name}' version {version} to production: {reason}")

def _dimension_scores(metrics, dimension):
    found = {
        'abs_error': metrics.get(f'grade_{dimension}/abs_error/mean'),
        'hallucination': metrics.get(HALLUCINATION_KEY),
    }
    return {name: float(value) for name, value in found.items() if value is not None}

def _passes_criteria(scores):
    return (scores.get('abs_error', 0) <= PROMOTION_MAE_THRESHOLD
            and scores.get('hallucination', 0) <= PROMOTION_HALLUCINATION_THRESHOLD)