import httpx

from app.core.config import get_settings
from app.repositories.interfaces import IngestionMetricBundle


def build_assessment_payload(
    metrics: IngestionMetricBundle,
    artifact_signals: dict[str, float],
    manual_text: str | None,
    jira_tickets: list[dict] | None = None,
    project_context_documents: list[dict] | None = None,
    repo_snapshot: dict | None = None,
) -> dict:
    # NOTE: `project_context_documents` carries extracted text from the files
    # uploaded via /api/v1/projects/{id}/documents. It is BACKGROUND CONTEXT
    # for the LLM about the project (project brief, requirements notes, etc.)
    # and is deliberately a separate top-level field from `artifact_metrics`
    # so the AI engine never conflates it with the `documentation` rubric
    # dimension — see collect_project_context_documents.
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
        "jira_tickets": jira_tickets or [],
        "artifact_metrics": artifact_signals,
        "project_context_documents": project_context_documents or [],
        # The repository's files at its latest commit (see
        # collect_repository_snapshot), so the final submission is graded,
        # not only the history. None when the snapshot could not be read.
        "repo_snapshot": repo_snapshot,
        "instructor_expectations": manual_text or "No instructor guidance provided.",
    }


# A full assessment is six sequential LLM calls (plus retries) on a local GPU model, so the
# read timeout is long, but it is finite: an unbounded wait leaves the job stuck in
# "ai_evaluating" forever when the engine hangs. Override with AI_ENGINE_TIMEOUT_SECONDS.
DEFAULT_AI_ENGINE_READ_TIMEOUT_SECONDS = 3600.0
_CONNECT_TIMEOUT_SECONDS = 10.0
_WRITE_TIMEOUT_SECONDS = 60.0
_POOL_TIMEOUT_SECONDS = 10.0
_TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})


class AIEngineError(RuntimeError):
    """The AI engine call failed. `kind` says how, `transient` whether retrying later may help.

    kind: "timeout" and "unavailable" are transient infrastructure failures; "rejected"
    (4xx), "engine_error" (5xx, e.g. every dimension failed) and "invalid_response" are
    not expected to change on an identical retry.
    """

    def __init__(self, message: str, *, kind: str, transient: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.transient = transient


def _ai_engine_timeout(settings: object) -> httpx.Timeout:
    configured = getattr(settings, "ai_engine_timeout_seconds", None)
    try:
        read_timeout = float(configured) if configured is not None else 0.0
    except (TypeError, ValueError):
        read_timeout = 0.0
    if read_timeout <= 0:
        read_timeout = DEFAULT_AI_ENGINE_READ_TIMEOUT_SECONDS
    return httpx.Timeout(
        connect=_CONNECT_TIMEOUT_SECONDS,
        read=read_timeout,
        write=_WRITE_TIMEOUT_SECONDS,
        pool=_POOL_TIMEOUT_SECONDS,
    )


def send_assessment_to_ai_engine(payload: dict, model_name: str | None = None) -> dict:
    settings = get_settings()
    base_url = settings.ai_engine_url.rstrip("/")
    selected_model = model_name or settings.default_model_name
    request_url = f"{base_url}/assess/sprint/data?modelname={selected_model}"
    timeout = _ai_engine_timeout(settings)

    try:
        # One-shot transport: the engine already retries each dimension, and resending a
        # whole assessment from here would only multiply GPU time. The timeout is bounded.
        response = httpx.post(request_url, json=payload, timeout=timeout)  # nosec B113
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise AIEngineError(
            f"AI engine did not answer within {timeout.read:.0f}s: {exc!r}",
            kind="timeout",
            transient=True,
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code >= 500:
            raise AIEngineError(
                f"AI engine failed with HTTP {status_code}: {exc.response.text}",
                kind="engine_error",
                transient=status_code in _TRANSIENT_STATUS_CODES,
            ) from exc
        raise AIEngineError(
            f"AI engine rejected the assessment payload: {exc.response.text}",
            kind="rejected",
            transient=False,
        ) from exc
    except httpx.HTTPError as exc:
        raise AIEngineError(
            f"AI engine request failed: {exc}", kind="unavailable", transient=True
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise AIEngineError(
            "AI engine returned a non-JSON assessment response.",
            kind="invalid_response",
            transient=False,
        ) from exc
