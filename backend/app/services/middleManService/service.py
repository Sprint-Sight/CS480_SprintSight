from app.repositories.interfaces import IngestionMetricBundle


def build_assessment_payload(
    metrics: IngestionMetricBundle,
    document_signals: dict[str, float],
    manual_text: str | None,
) -> dict:
    return {
        "sprint_context": {
            "course_id": metrics.course_id,
            "project_id": metrics.project_id,
            "sprint_id": metrics.sprint_id,
            "captured_at": metrics.captured_at.isoformat(),
        },
        "collaboration_metrics": {
            "commit_frequency": metrics.commit_frequency,
            "code_churn": metrics.code_churn,
            "pr_turnaround_hours": metrics.pr_turnaround_hours,
            "assigned_story_points": metrics.assigned_story_points,
            "completion_percent": metrics.completion_percent,
        },
        "commits": [commit.model_dump(mode="json") for commit in metrics.commits],
        "artifact_metrics": document_signals,
        "instructor_expectations": manual_text or "No instructor guidance provided.",
    }
