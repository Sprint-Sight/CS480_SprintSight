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


def _resolve_jira_auth(project: ProjectRecord) -> tuple[str, str, str]:
    settings = get_settings()
    if project.jira_api_token_encrypted:
        try:
            token = decrypt_secret(project.jira_api_token_encrypted)
        except CredentialDecryptionError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stored Jira credentials could not be decrypted. Re-save the API token.",
            ) from exc
        email = project.jira_email
        domain = normalize_jira_domain(project.jira_domain)
        if not email or not domain or not token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Jira credentials are incomplete for this project.",
            )
        return domain, email, token
    domain = normalize_jira_domain(settings.jira_domain) or ""
    if domain and settings.jira_email and settings.jira_api_token:
        return domain, settings.jira_email, settings.jira_api_token
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Jira credentials are not configured for this project.",
    )


def fetch_and_store_raw_jira_data(
    course_id: str,
    project_id: str,
    sprint_id: str,
    jira_project_key: str,
    project: ProjectRecord,
    jql: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    domain, email, api_token = _resolve_jira_auth(project)

    query = jql or f'project = "{jira_project_key}" ORDER BY updated DESC'
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
