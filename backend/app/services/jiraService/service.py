from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import IngestionMetricBundle
from app.schemas.assessment import IngestionRequest


# Mock Jira signal enrichment while DB and external adapters are pending.
def enrich_jira_metrics(payload: IngestionRequest) -> IngestionMetricBundle | None:
    return metrics_repo.get_metrics(payload.course_id, payload.project_id, payload.sprint_id)
