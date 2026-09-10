import httpx

from app.core.config import get_settings
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


def send_assessment_to_ai_engine(payload: dict, model_name: str | None = None) -> dict:
    settings = get_settings()
    base_url = settings.ai_engine_url.rstrip("/")
    selected_model = model_name or settings.default_model_name
    request_url = f"{base_url}/assess/sprint/data?modelname={selected_model}"

    try:
        # One-shot transport only. Do not retry and do not impose a fixed
        # client timeout that can prematurely force the job into failed state.
        response = httpx.post(request_url, json=payload, timeout=None)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"AI engine rejected the assessment payload: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"AI engine request failed: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("AI engine returned a non-JSON assessment response.") from exc
