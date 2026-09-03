from typing import Any

from app.schemas.assessment import JiraCleanedSnapshot, JiraTicket

NORMALIZATION_VERSION = "jira-ticket-v1"


class JiraNormalizationError(ValueError):
    pass


def _nested_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("displayName") or value.get("name") or value.get("accountId")
    return str(name).strip() if name else None


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


def normalize_jira_envelope(
    envelope: dict[str, Any],
    *,
    story_points_field: str | None = None,
) -> JiraCleanedSnapshot:
    required = ("jira_project_key", "course_id", "project_id", "sprint_id", "captured_at", "issues")
    missing = [field for field in required if field not in envelope]
    if missing:
        raise JiraNormalizationError(f"Jira envelope is missing: {', '.join(missing)}")
    issues = envelope["issues"]
    if not isinstance(issues, list):
        raise JiraNormalizationError("Jira envelope issues must be an array.")

    tickets: list[JiraTicket] = []
    for issue in issues:
        if not isinstance(issue, dict) or not issue.get("key"):
            raise JiraNormalizationError("Every Jira issue must contain a key.")
        fields = issue.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        summary = fields.get("summary") or ""
        tickets.append(
            JiraTicket(
                ticket_id=str(issue["key"]),
                summary=" ".join(str(summary).split()),
                assignee=_nested_name(fields.get("assignee")),
                status=_nested_name(fields.get("status")),
                issue_type=_nested_name(fields.get("issuetype")),
                story_points=_story_points(fields, story_points_field),
                sprint_id=envelope["sprint_id"],
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