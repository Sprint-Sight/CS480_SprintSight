from datetime import datetime, timezone

from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import IngestionMetricBundle
from app.schemas.assessment import IngestionRequest


# Mock metrics until live GitHub API integration is enabled.
def ingest_github_metrics(payload: IngestionRequest) -> IngestionMetricBundle:
    metrics = IngestionMetricBundle(
        course_id=payload.course_id,
        project_id=payload.project_id,
        sprint_id=payload.sprint_id,
        commit_frequency=18.5,
        code_churn=2364,
        pr_turnaround_hours=14.2,
        assigned_story_points=42,
        completion_percent=87.0,
        captured_at=datetime.now(timezone.utc),
    )
    metrics_repo.save_metrics(metrics)
    return metrics
