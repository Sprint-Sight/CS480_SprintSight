import re
from datetime import UTC, date, datetime
from typing import Any

from app.repositories.interfaces import UserRecord
from app.schemas.assessment import (
    JiraCleanedSnapshot,
    JiraIssueChange,
    JiraIssueChangeItem,
    JiraTicket,
)

NORMALIZATION_VERSION = "jira-ticket-v2"


class JiraNormalizationError(ValueError):
    pass


def _nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("displayName") or value.get("name") or value.get("accountId")
    return str(name).strip() if name else None


def _ticket_timestamp(
    fields: dict[str, Any],
    completion_date_field: str | None,
) -> datetime | None:
    raw = (
        fields.get(completion_date_field) if completion_date_field else None
    ) or fields.get("resolutiondate") or fields.get("resolutionDate")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None


def _sprint_identity(value: Any) -> str:
    normalized = str(value or "").strip().casefold()
    match = re.fullmatch(r"sprint[\s_-]*(.+)", normalized)
    if match:
        normalized = match.group(1).strip()
    return re.sub(r"[\s_-]+", "", normalized)


def _sprint_metadata_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [entry for item in value for entry in _sprint_metadata_entries(item)]
    if isinstance(value, dict):
        if "startDate" in value or "endDate" in value:
            return [value]
        return [entry for item in value.values() for entry in _sprint_metadata_entries(item)]
    if isinstance(value, str):
        pairs = re.findall(r"(id|name|startDate|endDate)=([^,\]]+)", value)
        if pairs:
            return [{key: item.strip() for key, item in pairs}]
    return []


def _sprint_dates(
    issues: list[dict[str, Any]],
    sprint_field: str,
    requested_sprint: str | None,
    sprint_start_date_field: str | None,
    sprint_end_date_field: str | None,
) -> tuple[date | None, date | None]:
    if sprint_start_date_field or sprint_end_date_field:
        custom_start_date = None
        custom_end_date = None
        for issue in issues:
            fields = issue.get("fields")
            if not isinstance(fields, dict):
                continue
            if custom_start_date is None and sprint_start_date_field:
                custom_start_date = _parse_date(fields.get(sprint_start_date_field))
            if custom_end_date is None and sprint_end_date_field:
                custom_end_date = _parse_date(fields.get(sprint_end_date_field))
            if custom_start_date and custom_end_date:
                return custom_start_date, custom_end_date
        if custom_start_date or custom_end_date:
            return custom_start_date, custom_end_date

    target = _sprint_identity(requested_sprint)
    for issue in issues:
        fields = issue.get("fields")
        if not isinstance(fields, dict):
            continue
        for sprint in _sprint_metadata_entries(fields.get(sprint_field)):
            candidates = (sprint.get("id"), sprint.get("name"))
            if target and not any(_sprint_identity(item) == target for item in candidates):
                continue
            start_date = _parse_date(sprint.get("startDate"))
            end_date = _parse_date(sprint.get("endDate"))
            if start_date or end_date:
                return start_date, end_date
    return None, None


def _issue_changelog(issue: dict[str, Any]) -> list[JiraIssueChange]:
    raw_changelog = issue.get("changelog")
    if not isinstance(raw_changelog, dict):
        return []
    histories = raw_changelog.get("histories") or raw_changelog.get("changeHistories") or []
    if not isinstance(histories, list):
        return []

    changes: list[JiraIssueChange] = []
    for history in histories:
        if not isinstance(history, dict) or not history.get("created"):
            continue
        created = history["created"]
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
        if not isinstance(created, datetime):
            continue
        raw_items = history.get("items")
        if not isinstance(raw_items, list):
            continue
        items = [
            JiraIssueChangeItem(
                field=str(item["field"]) if item.get("field") is not None else None,
                field_id=str(item["fieldId"]) if item.get("fieldId") is not None else None,
                from_value=str(item["from"]) if item.get("from") is not None else None,
                to_value=str(item["to"]) if item.get("to") is not None else None,
                from_string=str(item["fromString"])
                if item.get("fromString") is not None
                else None,
                to_string=str(item["toString"]) if item.get("toString") is not None else None,
            )
            for item in raw_items
            if isinstance(item, dict)
        ]
        changes.append(JiraIssueChange(created=created, items=items))
    return sorted(changes, key=lambda change: change.created)


def _story_points(fields: dict[str, Any], story_points_field: str | None) -> float | None:
    if not story_points_field:
        return None
    value = fields.get(story_points_field)
    if value is None or value == "":
        return None
    try:
        points = float(value)
    except (TypeError, ValueError):
        return None
    return points if points >= 0 else None


def _matches_requested_sprint(value: Any, sprint_id: str | None) -> bool:
    if not sprint_id:
        return True
    target = str(sprint_id).strip().lower()
    if not target:
        return True

    if isinstance(value, str):
        normalized = value.strip().lower()
        return normalized == target or normalized.replace(" ", "") == target.replace(" ", "")
    if isinstance(value, dict):
        for nested in value.values():
            if _matches_requested_sprint(nested, sprint_id):
                return True
        return False
    if isinstance(value, list):
        return any(_matches_requested_sprint(item, sprint_id) for item in value)
    return False


def _issue_type_from_fields(fields: dict) -> str | None:
    issue_type = fields.get("issuetype")
    if isinstance(issue_type, dict):
        name = issue_type.get("name")
        return str(name) if name else None
    return str(issue_type) if issue_type else None


def _normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().casefold() or None


def _issue_matches_requested_sprint(issue: dict[str, Any], sprint_id: str | None) -> bool:
    if not sprint_id:
        return True
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        return True
    for field_name in ("sprint", "sprints", "customfield_10020", "customfield_10018"):
        if field_name in fields and _matches_requested_sprint(fields[field_name], sprint_id):
            return True
    return True


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


def _resolve_student_id(
    assignee_id: str | None,
    assignee_name: str | None,
    assignee_email: str | None,
    project_member_ids: set[str],
    users_by_id: dict[str, UserRecord],
    ids_by_email: dict[str, list[str]],
    ids_by_name: dict[str, list[str]],
) -> str | None:
    """Resolve a Jira assignee to a SprintSight student ID.

    Resolution rules:
      1. Do NOT trust Jira account ID — it is not a reliable mapping to
         SprintSight student IDs unless explicitly configured elsewhere.
      2. Email match — only when exactly one active project member has that
         email (case-insensitive). Duplicate emails → null.
      3. Display-name match — only when exactly one active project member
         has that name (case-insensitive). Duplicate names → null.
      4. If email and name both match but to different students → null
         (conflicting signals).
      5. Otherwise → null (do not guess).
    """
    matched_by_email: str | None = None
    if assignee_email:
        normalized_email = assignee_email.strip().lower()
        email_candidates = [
            sid
            for sid in ids_by_email.get(normalized_email, [])
            if sid in project_member_ids
        ]
        if len(email_candidates) == 1:
            matched_by_email = email_candidates[0]
        elif len(email_candidates) > 1:
            return None  # ambiguous email

    matched_by_name: str | None = None
    if assignee_name:
        normalized_name = assignee_name.strip().lower()
        name_candidates = [
            sid
            for sid in ids_by_name.get(normalized_name, [])
            if sid in project_member_ids
        ]
        if len(name_candidates) == 1:
            matched_by_name = name_candidates[0]
        elif len(name_candidates) > 1:
            return None  # ambiguous name

    # Both matched — they must agree
    if matched_by_email and matched_by_name:
        if matched_by_email != matched_by_name:
            return None  # conflicting signals
        return matched_by_email

    # Only one matched
    if matched_by_email:
        return matched_by_email
    if matched_by_name:
        return matched_by_name

    return None


def normalize_jira_envelope(
    envelope: dict[str, Any],
    *,
    story_points_field: str | None = None,
    sprint_field: str = "customfield_10020",
    completion_date_field: str | None = None,
    sprint_start_date_field: str | None = None,
    sprint_end_date_field: str | None = None,
    users_by_id: dict[str, UserRecord] | None = None,
    ids_by_email: dict[str, list[str]] | None = None,
    ids_by_name: dict[str, list[str]] | None = None,
    project_member_ids: set[str] | None = None,
) -> JiraCleanedSnapshot:
    required = ("jira_project_key", "course_id", "project_id", "sprint_id", "captured_at", "issues")
    missing = [field for field in required if field not in envelope]
    if missing:
        raise JiraNormalizationError(f"Jira envelope is missing: {', '.join(missing)}")
    issues = envelope["issues"]
    if not isinstance(issues, list):
        raise JiraNormalizationError("Jira envelope issues must be an array.")

    requested_sprint = str(envelope["sprint_id"]).strip() or None
    sprint_start_date, sprint_end_date = _sprint_dates(
        issues,
        sprint_field,
        requested_sprint,
        sprint_start_date_field,
        sprint_end_date_field,
    )
    tickets: list[JiraTicket] = []
    for issue in issues:
        if not isinstance(issue, dict) or not issue.get("key"):
            raise JiraNormalizationError("Every Jira issue must contain a key.")
        if not _issue_matches_requested_sprint(issue, requested_sprint):
            continue
        fields = issue.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        summary = fields.get("summary") or ""
        assignee_id, assignee_name, assignee_email = _assignee_from_fields(fields)

        student_id = _resolve_student_id(
            assignee_id,
            assignee_name,
            assignee_email,
            project_member_ids or set(),
            users_by_id or {},
            ids_by_email or {},
            ids_by_name or {},
        )

        tickets.append(
            JiraTicket(
                ticket_id=str(issue["key"]),
                summary=" ".join(str(summary).split()),
                assignee=assignee_name,
                student_id=student_id,
                status=_nested_name(fields.get("status")),
                issue_type=_nested_name(fields.get("issuetype")),
                story_points=_story_points(fields, story_points_field),
                sprint_id=envelope["sprint_id"],
                timestamp=_ticket_timestamp(fields, completion_date_field),
                changelog=_issue_changelog(issue),
            )
        )

    tickets.sort(key=lambda ticket: ticket.ticket_id)
    return JiraCleanedSnapshot(
        normalization_version=NORMALIZATION_VERSION,
        jira_project_key=str(envelope["jira_project_key"]),
        course_id=str(envelope["course_id"]),
        project_id=str(envelope["project_id"]),
        sprint_id=str(envelope["sprint_id"]),
        captured_at=envelope["captured_at"],
        sprint_start_date=sprint_start_date,
        sprint_end_date=sprint_end_date,
        sprint_field=sprint_field,
        story_points_field=story_points_field,
        completion_date_field=completion_date_field,
        sprint_start_date_field=sprint_start_date_field,
        sprint_end_date_field=sprint_end_date_field,
        changelog_captured=envelope.get("changelog_captured") is True,
        tickets=tickets,
    )