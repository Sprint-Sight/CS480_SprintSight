from datetime import datetime
from typing import Any

from app.repositories.interfaces import UserRecord
from app.schemas.assessment import JiraCleanedSnapshot, JiraTicket

NORMALIZATION_VERSION = "jira-ticket-v1"


class JiraNormalizationError(ValueError):
    pass


def _nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("displayName") or value.get("name") or value.get("accountId")
    return str(name).strip() if name else None


def _ticket_timestamp(fields: dict[str, Any]) -> datetime | None:
    raw = fields.get("updated") or fields.get("statuscategorychangedate") or fields.get("created")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


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
                timestamp=_ticket_timestamp(fields),
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
        tickets=tickets,
    )