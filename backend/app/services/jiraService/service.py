# backend/app/services/jiraService/service.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import fmean, pstdev
from uuid import uuid4

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.credential_crypto import (
    CredentialDecryptionError,
    decrypt_secret,
    normalize_jira_domain,
)
from app.core.storage import storage
from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import (
    IngestionMetricBundle,
    JiraIngestionRunRecord,
    JiraIngestionRunRepository,
    ProjectRecord,
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.assessment import IngestionRequest
from app.schemas.jira_outlier import (
    JiraContributionOutlierReport,
    JiraContributionOutlierResponse,
    JiraContributionTicketEvidence,
)

# Same constant as peer eval.
OUTLIER_Z_THRESHOLD = 1.0


# ---------------------------------------------------------------------------
# Mock enrichment (while DB and external adapters are pending)
# ---------------------------------------------------------------------------
def enrich_jira_metrics(payload: IngestionRequest) -> IngestionMetricBundle | None:
    return metrics_repo.get_metrics(payload.course_id, payload.project_id, payload.sprint_id)


# ---------------------------------------------------------------------------
# Jira HTTP helpers
# ---------------------------------------------------------------------------
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
        detail = (
            "Jira project or API endpoint was not found. Check the project "
            "Jira URL and jira_project_key."
        )
    elif status_code == 410:
        detail = (
            "Jira retired the old search API. Restart the backend so it uses "
            "/rest/api/3/search/jql."
        )
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
    sprint_field = (
        get_settings().jira_sprint_field or "customfield_10020"
    ).strip() or "customfield_10020"
    sprint_value = _normalize_jira_sprint_value(sprint_id)
    if sprint_value:
        field_expr = sprint_field
        if sprint_field.startswith("customfield_"):
            field_expr = f"cf[{sprint_field.removeprefix('customfield_')}]"
        query = f'{query} AND {field_expr} = "{sprint_value}"'
    return f"{query} ORDER BY updated DESC"


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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not retrieve Jira data."
        ) from exc

    captured_at = datetime.now(UTC)
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
    object_key = (
        f"raw/jira/{course_id}/{project_id}/{sprint_id}/"
        f"{captured_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4()}.json"
    )
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


# ---------------------------------------------------------------------------
# Contribution outlier detection
# ---------------------------------------------------------------------------
def _mean_and_population_stdev(values: list[float]) -> tuple[float | None, float | None]:
    """Return the mean and population standard deviation for the cohort.

    The enrolled students form the full population we are comparing against,
    so population standard deviation is used rather than the sample estimate.
    """
    if not values:
        return None, None
    mean = fmean(values)
    standard_deviation = pstdev(values) if len(values) >= 2 else None
    return mean, standard_deviation


def _z_score(value: float, mean: float | None, standard_deviation: float | None) -> float | None:
    if mean is None or standard_deviation is None or standard_deviation == 0:
        return None
    return (value - mean) / standard_deviation


def _is_outlier(z: float | None) -> bool:
    return z is not None and abs(z) >= OUTLIER_Z_THRESHOLD


def _round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _coerce_story_points(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        points = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return points if points >= 0 else None


def _story_points_from_fields(fields: dict) -> float:
    settings = get_settings()
    candidates = [
        settings.jira_story_points_field,
        "customfield_10016",
        "customfield_10009",
        "customfield_10004",
        "story_points",
        "storyPoints",
        "points",
    ]
    for field_name in dict.fromkeys(candidates):
        if field_name and field_name in fields:
            points = _coerce_story_points(fields[field_name])
            if points is not None:
                return points
    return 0.0


def _assignee_from_fields(fields: dict) -> tuple[str | None, str | None, str | None]:
    """Return (assignee id/account id, display name, email) for a raw issue."""
    assignee = fields.get("assignee")
    if isinstance(assignee, dict):
        assignee_id = assignee.get("id") or assignee.get("accountId")
        display_name = assignee.get("displayName")
        email = assignee.get("emailAddress")
        return (
            str(assignee_id) if assignee_id else None,
            str(display_name) if display_name else None,
            str(email) if email else None,
        )
    if isinstance(assignee, str) and assignee.strip():
        return None, assignee.strip(), None
    return None, None, None


def _issue_type_from_fields(fields: dict) -> str | None:
    issue_type = fields.get("issuetype")
    if isinstance(issue_type, dict):
        name = issue_type.get("name")
        return str(name) if name else None
    return str(issue_type) if issue_type else None


def _status_from_fields(fields: dict) -> str | None:
    status = fields.get("status")
    if isinstance(status, dict):
        name = status.get("name")
        return str(name) if name else None
    return str(status) if status else None


@dataclass
class _ContributionTicket:
    ticket_id: str
    summary: str
    story_points: float
    assignee_id: str | None
    assignee_name: str | None
    assignee_email: str | None
    status: str | None
    issue_type: str | None
    project_id: str
    sprint_id: str | None


def _tickets_from_run(run: JiraIngestionRunRecord) -> list[_ContributionTicket]:
    """Read tickets from either a cleaned snapshot or a raw snapshot dict.

    Ingestion normally stores a ``JiraCleanedSnapshot`` (``tickets`` list), but
    older runs and tests may still hold the raw ``issues`` payload. Supporting
    both keeps the endpoint usable while data is being backfilled.
    """
    snapshot = run.cleaned_snapshot
    if snapshot is None:
        return []

    tickets: list[_ContributionTicket] = []

    if isinstance(snapshot, dict):
        raw_issues = snapshot.get("issues")
        if raw_issues is None:
            raw_issues = snapshot.get("tickets")
        for issue in raw_issues or []:
            if not isinstance(issue, dict):
                continue
            # Already cleaned (dict form of JiraTicket).
            if "ticket_id" in issue:
                tickets.append(
                    _ContributionTicket(
                        ticket_id=str(issue.get("ticket_id") or ""),
                        summary=str(issue.get("summary") or ""),
                        story_points=_coerce_story_points(issue.get("story_points")) or 0.0,
                        assignee_id=None,
                        assignee_name=str(issue["assignee"]) if issue.get("assignee") else None,
                        assignee_email=None,
                        status=str(issue["status"]) if issue.get("status") else None,
                        issue_type=str(issue["issue_type"]) if issue.get("issue_type") else None,
                        project_id=str(issue.get("project_id") or run.project_id),
                        sprint_id=str(issue.get("sprint_id") or run.sprint_id)
                        if issue.get("sprint_id") or run.sprint_id
                        else None,
                    )
                )
                continue

            # Raw Jira issue envelope.
            fields = issue.get("fields")
            if not isinstance(fields, dict):
                fields = {}
            assignee_id, assignee_name, assignee_email = _assignee_from_fields(fields)
            tickets.append(
                _ContributionTicket(
                    ticket_id=str(issue.get("key") or ""),
                    summary=str(fields.get("summary") or ""),
                    story_points=_story_points_from_fields(fields),
                    assignee_id=assignee_id,
                    assignee_name=assignee_name,
                    assignee_email=assignee_email,
                    status=_status_from_fields(fields),
                    issue_type=_issue_type_from_fields(fields),
                    project_id=run.project_id,
                    sprint_id=run.sprint_id,
                )
            )
        return tickets

    # Pydantic JiraCleanedSnapshot.
    for ticket in getattr(snapshot, "tickets", []) or []:
        tickets.append(
            _ContributionTicket(
                ticket_id=str(getattr(ticket, "ticket_id", "") or ""),
                summary=str(getattr(ticket, "summary", "") or ""),
                story_points=_coerce_story_points(getattr(ticket, "story_points", None)) or 0.0,
                assignee_id=getattr(ticket, "student_id", None),
                assignee_name=getattr(ticket, "assignee", None),
                assignee_email=None,
                status=getattr(ticket, "status", None),
                issue_type=getattr(ticket, "issue_type", None),
                project_id=run.project_id,
                sprint_id=getattr(ticket, "sprint_id", None) or run.sprint_id,
            )
        )
    return tickets


def _resolve_assignee_id(
    ticket: _ContributionTicket,
    enrolled_ids: set[str],
    users_by_id: dict[str, UserRecord],
    ids_by_email: dict[str, str],
    ids_by_name: dict[str, str],
) -> str | None:
    """Map a ticket assignee to an enrolled student id.

    Raw issues carry Jira account ids, while normalized snapshots carry display
    names. Try the id first, then email and display name.
    """
    if ticket.assignee_id and ticket.assignee_id in enrolled_ids:
        return ticket.assignee_id
    if ticket.assignee_id and ticket.assignee_id in users_by_id:
        return ticket.assignee_id
    for candidate in (ticket.assignee_email, ticket.assignee_name):
        if not candidate:
            continue
        normalized = candidate.strip().lower()
        student_id = ids_by_email.get(normalized) or ids_by_name.get(normalized)
        if student_id in enrolled_ids:
            return student_id
    return None


@dataclass
class _CourseContributionData:
    course_id: str
    enrolled_ids: list[str]
    users_by_id: dict[str, UserRecord]
    totals_by_student: dict[str, float]
    tickets_by_student: dict[str, list[JiraContributionTicketEvidence]]
    project_by_student: dict[str, str]
    course_mean: float | None
    course_stdev: float | None
    students_with_jira_data: int = 0
    students_below_average: int = 0
    extra: dict[str, object] = field(default_factory=dict)


def _load_course_contributions(
    course_id: str,
    jira_repo: JiraIngestionRunRepository,
    user_repo: UserRepository,
    project_repo: ProjectRepository,
) -> _CourseContributionData:
    enrolled_ids = project_repo.list_enrolled_student_ids(course_id)
    enrolled_set = set(enrolled_ids)

    users_by_id: dict[str, UserRecord] = {}
    ids_by_email: dict[str, str] = {}
    ids_by_name: dict[str, str] = {}
    for student_id in enrolled_ids:
        user = user_repo.get_by_id(student_id)
        if user is None:
            continue
        users_by_id[student_id] = user
        if user.email:
            ids_by_email[user.email.strip().lower()] = student_id
        if user.full_name:
            ids_by_name[user.full_name.strip().lower()] = student_id

    projects = project_repo.list_projects(course_id)
    latest_runs: list[JiraIngestionRunRecord] = []
    project_by_student: dict[str, str] = {}
    any_runs = False
    for project in projects:
        for member_id in project_repo.list_member_ids(project.id):
            if member_id in enrolled_set:
                project_by_student.setdefault(member_id, project.id)
        project_runs = jira_repo.list_project_runs(project.id)
        if project_runs:
            any_runs = True
        cleaned_runs = [run for run in project_runs if run.cleaned_snapshot]
        if cleaned_runs:
            latest_runs.append(max(cleaned_runs, key=lambda run: run.captured_at))

    if not any_runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Jira ingestion data for this course",
        )
    if not latest_runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest Jira run has not been normalised yet",
        )

    totals_by_student: dict[str, float] = {student_id: 0.0 for student_id in enrolled_ids}
    tickets_by_student: dict[str, list[JiraContributionTicketEvidence]] = {
        student_id: [] for student_id in enrolled_ids
    }

    for run in latest_runs:
        for ticket in _tickets_from_run(run):
            if not ticket.ticket_id:
                continue
            student_id = _resolve_assignee_id(
                ticket,
                enrolled_set,
                users_by_id,
                ids_by_email,
                ids_by_name,
            )
            if student_id is None:
                # Unassigned tickets and tickets for students outside the course
                # are not part of the course baseline.
                continue
            totals_by_student[student_id] += ticket.story_points
            tickets_by_student[student_id].append(
                JiraContributionTicketEvidence(
                    ticket_id=ticket.ticket_id,
                    summary=ticket.summary,
                    story_points=ticket.story_points,
                    status=ticket.status,
                    issue_type=ticket.issue_type,
                    project_id=ticket.project_id,
                    sprint_id=ticket.sprint_id,
                )
            )

    for student_tickets in tickets_by_student.values():
        student_tickets.sort(key=lambda evidence: evidence.ticket_id)

    course_mean, course_stdev = _mean_and_population_stdev(
        [float(totals_by_student[student_id]) for student_id in enrolled_ids]
    )
    students_with_jira_data = sum(
        1 for student_id in enrolled_ids if tickets_by_student[student_id]
    )
    students_below_average = 0
    if course_mean is not None:
        students_below_average = sum(
            1
            for student_id in enrolled_ids
            if totals_by_student[student_id] < course_mean
        )

    return _CourseContributionData(
        course_id=course_id,
        enrolled_ids=enrolled_ids,
        users_by_id=users_by_id,
        totals_by_student=totals_by_student,
        tickets_by_student=tickets_by_student,
        project_by_student=project_by_student,
        course_mean=course_mean,
        course_stdev=course_stdev,
        students_with_jira_data=students_with_jira_data,
        students_below_average=students_below_average,
    )


def _build_student_response(
    data: _CourseContributionData,
    student_id: str,
) -> JiraContributionOutlierResponse:
    total_points = data.totals_by_student[student_id]
    tickets = data.tickets_by_student[student_id]
    total_tickets = len(tickets)
    average_per_ticket = (
        round(total_points / total_tickets, 2) if total_tickets else 0.0
    )

    z = _z_score(float(total_points), data.course_mean, data.course_stdev)
    is_outlier = _is_outlier(z)
    direction = None
    if is_outlier and z is not None:
        direction = "high" if z > 0 else "low"

    user = data.users_by_id.get(student_id)
    return JiraContributionOutlierResponse(
        student_id=student_id,
        student_full_name=user.full_name if user else "Unknown",
        course_id=data.course_id,
        project_id=data.project_by_student.get(student_id),
        total_tickets=total_tickets,
        total_story_points=float(total_points),
        average_points_per_ticket=average_per_ticket,
        course_average_total_points=_round_or_none(data.course_mean),
        course_total_score_std_dev=_round_or_none(data.course_stdev),
        contribution_z_score=_round_or_none(z),
        is_contribution_outlier=is_outlier,
        outlier_direction=direction,
        students_below_course_average=data.students_below_average,
        enrolled_student_count=len(data.enrolled_ids),
        students_with_jira_data=data.students_with_jira_data,
        tickets=tickets,
    )


def get_jira_contribution_outlier(
    course_id: str,
    student_id: str,
    jira_repo: JiraIngestionRunRepository,
    user_repo: UserRepository,
    project_repo: ProjectRepository,
) -> JiraContributionOutlierResponse:
    """Jira-contribution outlier report for a single student in a course.

    Faculty-only access is enforced in the route layer (``require_faculty``).
    """
    data = _load_course_contributions(
        course_id,
        jira_repo=jira_repo,
        user_repo=user_repo,
        project_repo=project_repo,
    )
    if student_id not in data.totals_by_student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not enrolled in this course",
        )
    return _build_student_response(data, student_id)


def get_jira_contribution_outliers(
    course_id: str,
    jira_repo: JiraIngestionRunRepository,
    user_repo: UserRepository,
    project_repo: ProjectRepository,
    only_outliers: bool = False,
) -> JiraContributionOutlierReport:
    """Course-wide contribution report with per-student evidence.

    When ``only_outliers`` is true the ``students`` list is filtered to flagged
    students, but the course baseline and ``outlier_count`` still describe the
    whole enrolled cohort.
    """
    data = _load_course_contributions(
        course_id,
        jira_repo=jira_repo,
        user_repo=user_repo,
        project_repo=project_repo,
    )
    responses = [
        _build_student_response(data, student_id) for student_id in data.enrolled_ids
    ]
    responses.sort(
        key=lambda response: (-response.total_story_points, response.student_full_name.lower())
    )
    outlier_count = sum(1 for response in responses if response.is_contribution_outlier)
    if only_outliers:
        responses = [response for response in responses if response.is_contribution_outlier]

    return JiraContributionOutlierReport(
        course_id=course_id,
        course_average_total_points=_round_or_none(data.course_mean),
        course_total_score_std_dev=_round_or_none(data.course_stdev),
        enrolled_student_count=len(data.enrolled_ids),
        students_with_jira_data=data.students_with_jira_data,
        students_below_course_average=data.students_below_average,
        outlier_count=outlier_count,
        students=responses,
    )
