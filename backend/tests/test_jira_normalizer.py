from datetime import datetime, timezone

import pytest

from app.services.jiraService.normalizer import JiraNormalizationError, normalize_jira_envelope


def envelope(issues: list[dict]) -> dict:
    return {
        "source": "jira",
        "captured_at": datetime(2026, 9, 2, tzinfo=timezone.utc),
        "jira_project_key": "DS3",
        "course_id": "course-1",
        "project_id": "project-1",
        "sprint_id": "sprint-2",
        "issues": issues,
    }


def test_normalizes_screenshot_ticket_fields_and_sorts_tickets() -> None:
    result = normalize_jira_envelope(
        envelope([
            {
                "key": "DS3-2",
                "expand": "irrelevant transport data",
                "fields": {
                    "summary": "  Build   report  ",
                    "assignee": {"displayName": "Student One"},
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Story"},
                    "customfield_10016": 5,
                },
            },
            {"key": "DS3-1", "fields": {"summary": "Backlog"}},
        ]),
        story_points_field="customfield_10016",
    )

    assert [ticket.ticket_id for ticket in result.tickets] == ["DS3-1", "DS3-2"]
    assert result.tickets[1].model_dump() == {
        "ticket_id": "DS3-2",
        "summary": "Build report",
        "assignee": "Student One",
        "status": "In Progress",
        "issue_type": "Story",
        "story_points": 5.0,
        "sprint_id": "sprint-2",
        "timestamp": None,
    }
    assert result.normalization_version == "jira-ticket-v1"


def test_missing_values_are_preserved_as_null() -> None:
    result = normalize_jira_envelope(envelope([{"key": "DS3-3", "fields": {"summary": None}}]))

    assert result.tickets[0].assignee is None
    assert result.tickets[0].status is None
    assert result.tickets[0].issue_type is None
    assert result.tickets[0].story_points is None


def test_rejects_issue_without_key() -> None:
    with pytest.raises(JiraNormalizationError, match="must contain a key"):
        normalize_jira_envelope(envelope([{"fields": {"summary": "Missing key"}}]))
