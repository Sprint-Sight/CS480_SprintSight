import mlflow, logging
from mlflow.exceptions import MlflowException
from mlflow.genai.review_queues import ReviewQueue, create_review_queue, add_items_to_review_queue, get_review_queue, list_review_queue_items

log = logging.getLogger(__name__)

TAG_FLAG = "needs review"
TAG_REASONS = "review reasons"

def get_review_queue_from_id(queue_id: str) -> ReviewQueue:
    return get_review_queue(queue_id=queue_id)

def is_trace_in_review_queue(queue_id: str, trace_id: str) -> bool:
    items = list_review_queue_items(queue_id=queue_id)
    return any(item.item_id == trace_id for item in items)

def add_to_review_queue(queue_name: str, traces_id: list[str]) -> None: # List of trace_ids

    try: # Get the queue ID by name
        queue_id = get_review_queue(name=queue_name).queue_id
        log.info("Retrieved queue '%s' (ID: %s)", queue_name, queue_id)
    except MlflowException as e: # if it doesn't exist, create it
        if e.error_code == "RESOURCE_DOES_NOT_EXIST": # If the queue doesn't exist, create it
            log.info("Review queue '%s' does not exist yet, creating it...", queue_name)
            queue_id = create_review_queue(name=queue_name, queue_type="user").queue_id
            log.info("Created review queue '%s' (ID: %s)", queue_name, queue_id)
        else: # Error because of some other reason, re-raise it
            raise

    try: # After getting the queue ID, add the traces to the review queue
        add_items_to_review_queue(queue_id=queue_id, item_ids=traces_id)
        log.info("Added traces %s to review queue '%s' (ID: %s)", traces_id, queue_name, queue_id)
        print(f"\nAdded traces {traces_id} to review queue '{queue_name}' (ID: {queue_id})\n")
    except Exception as e:
        log.exception("Could not flag trace %s for review", traces_id)

# def flag_for_review(trace_id: str, reason: str, queue_name: str):
#     ok = True
#     try:
#         add_to_review_queue(queue_name=queue_name, traces_id=[trace_id])
#     except Exception:
#         ok = False
#         log.exception("Could not add trace %s to review queue '%s'", trace_id, queue_name)

#     try: # Set tags on the trace to indicate it needs review and the reason
#         client, existing = mlflow.MlflowClient, None
#         try:
#             existing = client.get_trace(trace_id).info.tags.get(TAG_REASONS)
#         except Exception:
#             log.warning("Could not retrieve existing tags for trace %s", trace_id)
#         client.set_trace_tag(trace_id, TAG_FLAG, "true")
#         client.set_trace_tag(trace_id, TAG_REASONS, existing + "; " + reason if existing else reason)
#     except Exception:
#         ok = False
#         log.exception("Could not set tags for trace %s", trace_id)
#     return ok