from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import IngestionMetricBundle
from app.schemas.assessment import IngestionRequest


# Mock Jira signal enrichment while DB and external adapters are pending.
def enrich_jira_metrics(payload: IngestionRequest) -> IngestionMetricBundle | None:
    return metrics_repo.get_metrics(payload.course_id, payload.project_id, payload.sprint_id)

import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.credential_crypto import CredentialDecryptionError, decrypt_secret, normalize_jira_domain
from app.core.storage import storage
from app.repositories.interfaces import ProjectRecord


def _extract_jira_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:300]
    if isinstance(payload, dict):
        error_messages = payload.get("errorMessages")
        if isinstance(error_messages, list) and error_messages:
            return " ".join(str(item) for item in error_messages)
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)
    return ""


def _jira_status_error_detail(exc: httpx.HTTPStatusError) -> str:
    status_code = exc.response.status_code
    if status_code in (401, 403):
        detail = "Jira rejected the credentials or the account lacks access to this project."
    elif status_code == 404:
        detail = "Jira project or API endpoint was not found. Check the project Jira URL and jira_project_key."
    elif status_code == 410:
        detail = "Jira retired the old search API. Restart the backend so it uses /rest/api/3/search/jql."
    else:
        detail = f"Jira returned HTTP {status_code}. Check the project key and JQL."
    extra = _extract_jira_error_text(exc.response)
    return f"{detail} {extra}".strip() if extra else detail


def _resolve_jira_auth(
    project: ProjectRecord,
    instructor_credentials: tuple[str, str] | None = None,
) -> tuple[str, str, str]:
    settings = get_settings()
    domain = normalize_jira_domain(project.jira_domain) or normalize_jira_domain(settings.jira_domain) or ""
    if instructor_credentials:
        email, api_token = instructor_credentials
        if domain and email and api_token:
            return domain, email, api_token
    if project.jira_api_token_encrypted:
        try:
            token = decrypt_secret(project.jira_api_token_encrypted)
        except CredentialDecryptionError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Jira credentials could not be decrypted. Re-save the API token.",
            ) from exc
        email = project.jira_email
        project_domain = normalize_jira_domain(project.jira_domain)
        if not email or not project_domain or not token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jira credentials are incomplete for this project.",
            )
        return project_domain, email, token
    if domain and settings.jira_email and settings.jira_api_token:
        return domain, settings.jira_email, settings.jira_api_token
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Jira credentials are not configured for this project.",
    )


def validate_jira_credentials(
    domain: str,
    email: str,
    api_token: str,
    project_key: str | None = None,
) -> None:
    """Validate Jira credentials without returning or logging the token."""
    settings = get_settings()
    normalized_domain = normalize_jira_domain(domain)
    if not normalized_domain or not email or not api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jira email, domain, and API token are required.",
        )

    try:
        with httpx.Client(
            base_url=f"https://{normalized_domain}",
            auth=(email, api_token),
            timeout=settings.jira_timeout_seconds,
            headers={"Accept": "application/json"},
        ) as client:
            if project_key:
                response = client.post(
                    "/rest/api/3/search/jql",
                    json={
                        "jql": f'project = "{project_key}"',
                        "maxResults": 1,
                        "fields": ["id"],
                    },
                )
            else:
                response = client.get("/rest/api/3/myself")
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403, 404):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Jira rejected the credentials or project access.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_jira_status_error_detail(exc),
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not validate Jira credentials.",
        ) from exc


def _normalize_jira_sprint_value(sprint_id: str | None) -> str | None:
    if sprint_id is None:
        return None
    value = str(sprint_id).strip()
    if not value:
        return None
    value = value.replace("_", "-")
    if value.lower().startswith("sprint-"):
        suffix = value.split("-", 1)[1].strip()
        if suffix:
            return f"Sprint {suffix}"
    if value.lower().startswith("sprint "):
        return value.title()
    if value.lower() == "sprint":
        return "Sprint"
    if "Sprint " in value:
        return value
    return value


def _build_jira_search_jql(jira_project_key: str, sprint_id: str | None, jql: str | None) -> str:
    if jql:
        return jql
    query = f'project = "{jira_project_key}"'
    sprint_field = (get_settings().jira_sprint_field or "customfield_10020").strip() or "customfield_10020"
    sprint_value = _normalize_jira_sprint_value(sprint_id)
    if sprint_value:
        field_expr = sprint_field
        if sprint_field.startswith("customfield_"):
            field_expr = f"cf[{sprint_field.removeprefix('customfield_')}]"
        query = f'{query} AND {field_expr} = "{sprint_value}"'
    return f'{query} ORDER BY updated DESC'


def fetch_and_store_raw_jira_data(
    course_id: str,
    project_id: str,
    sprint_id: str,
    jira_project_key: str,
    project: ProjectRecord,
    jql: str | None = None,
    instructor_credentials: tuple[str, str] | None = None,
) -> dict[str, object]:
    settings = get_settings()
    domain, email, api_token = _resolve_jira_auth(project, instructor_credentials)

    query = _build_jira_search_jql(jira_project_key, sprint_id, jql)
    issues: list[dict] = []
    next_page_token: str | None = None
    page_size = 100

    try:
        with httpx.Client(
            base_url=f"https://{domain}",
            auth=(email, api_token),
            timeout=settings.jira_timeout_seconds,
            headers={"Accept": "application/json"},
        ) as client:
            while True:
                body: dict[str, object] = {
                    "jql": query,
                    "maxResults": page_size,
                    "fields": ["*all"],
                }
                if next_page_token:
                    body["nextPageToken"] = next_page_token
                response = client.post("/rest/api/3/search/jql", json=body)
                response.raise_for_status()
                page = response.json()
                page_issues = page.get("issues", [])
                issues.extend(page_issues)
                next_page_token = page.get("nextPageToken")
                if not page_issues or not next_page_token:
                    break
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_jira_status_error_detail(exc),
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not retrieve Jira data.") from exc

    captured_at = datetime.now(timezone.utc)
    raw_document = {
        "source": "jira",
        "captured_at": captured_at.isoformat(),
        "jira_domain": domain,
        "jira_project_key": jira_project_key,
        "jql": query,
        "course_id": course_id,
        "project_id": project_id,
        "sprint_id": sprint_id,
        "issues": issues,
    }
    object_key = f"raw/jira/{course_id}/{project_id}/{sprint_id}/{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4()}.json"
    storage.upload(
        settings.minio_bucket_raw,
        object_key,
        json.dumps(raw_document, ensure_ascii=True, separators=(",", ":")).encode("utf-8"),
        "application/json",
    )
    return {
        "object_key": object_key,
        "bucket": settings.minio_bucket_raw,
        "captured_at": captured_at,
        "issue_count": len(issues),
        "jira_project_key": jira_project_key,
        "jql": query,
    }
