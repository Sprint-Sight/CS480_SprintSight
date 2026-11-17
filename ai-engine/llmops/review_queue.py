import logging

import mlflow
from mlflow.exceptions import MlflowException
from mlflow.genai.review_queues import (
    add_items_to_review_queue,
    create_review_queue,
    get_review_queue,
)

from llmops import experiments

log = logging.getLogger(__name__)

FLAGGED_QUEUE = 'flagged_runs'
TAG_FLAG = "needs review"
TAG_REASONS = "review reasons"

# queue_name is kept for callers; every flag now goes to 1 shared research queue
def add_to_review_queue(queue_name: str, traces_id: list[str]) -> None: # List of trace_ids
    try:
        experiment_id = _experiment_id_for(traces_id[0])
        try:
            queue_id = get_review_queue(name=FLAGGED_QUEUE, experiment_id=experiment_id).queue_id
        except MlflowException as e:
            if e.error_code != "RESOURCE_DOES_NOT_EXIST":
                raise
            queue_id = create_review_queue(
                FLAGGED_QUEUE, queue_type="custom", experiment_id=experiment_id
            ).queue_id
        add_items_to_review_queue(queue_id=queue_id, item_ids=traces_id)
        log.info("Added traces %s to review queue '%s' (ID: %s)", traces_id, FLAGGED_QUEUE, queue_id)
    except Exception:  # flagging must never break grading or judging
        log.exception("Could not flag traces %s for review", traces_id)

def _experiment_id_for(trace_id: str) -> str:
    """The trace's own experiment; the production one if the trace cannot be fetched."""
    client = mlflow.MlflowClient()
    try:
        return client.get_trace(trace_id).info.experiment_id
    except Exception:
        log.warning("Could not read trace %s; using the production experiment.", trace_id)
        return client.get_experiment_by_name(experiments.PRODUCTION).experiment_id