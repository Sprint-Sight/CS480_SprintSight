from datetime import UTC, datetime
from typing import TypedDict

import pytest

from app.repositories.interfaces import Role, UserRecord
from app.services.jiraService.normalizer import JiraNormalizationError, normalize_jira_envelope


class _MemberLookupMaps(TypedDict):
    users_by_id: dict[str, UserRecord]
    ids_by_email: dict[str, list[str]]
    ids_by_name: dict[str, list[str]]
    project_member_ids: set[str]


def envelope(issues: list[dict]) -> dict:
    return {
        "source": "jira",
        "captured_at": datetime(2026, 9, 2, tzinfo=UTC),
        "jira_project_key": "DS3",
        "course_id": "course-1",
        "project_id": "project-1",
        "sprint_id": "sprint-2",
        "issues": issues,
    }


def _member_map(student_id: str, email: str, name: str) -> _MemberLookupMaps:
    """Build the lookup maps for a single project member."""
    return {
        "users_by_id": {
            student_id: UserRecord(
                id=student_id,
                email=email,
                full_name=name,
                role=Role.STUDENT,
                hashed_password="x",
                is_active=True,
            )
        },
        "ids_by_email": {email.strip().lower(): [student_id]},
        "ids_by_name": {name.strip().lower(): [student_id]},
        "project_member_ids": {student_id},
    }


def test_normalizes_screenshot_ticket_fields_and_sorts_tickets() -> None:
    result = normalize_jira_envelope(
        envelope(
            [
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
            ]
        ),
        story_points_field="customfield_10016",
    )

    assert [ticket.ticket_id for ticket in result.tickets] == ["DS3-1", "DS3-2"]
    assert result.tickets[1].model_dump() == {
        "ticket_id": "DS3-2",
        "summary": "Build report",
        "assignee": "Student One",
        "student_id": None,
        "status": "In Progress",
        "status_category": None,
        "issue_type": "Story",
        "story_points": 5.0,
        "sprint_id": "sprint-2",
        "created_at": None,
        "timestamp": None,
        "changelog": [],
    }
    assert result.normalization_version == "jira-ticket-v2"


def test_missing_values_are_preserved_as_null() -> None:
    result = normalize_jira_envelope(envelope([{"key": "DS3-3", "fields": {"summary": None}}]))

    assert result.tickets[0].assignee is None
    assert result.tickets[0].status is None
    assert result.tickets[0].issue_type is None
    assert result.tickets[0].story_points is None


def test_normalizes_jira_status_category() -> None:
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "DS3-CUSTOM-DONE",
                    "fields": {
                        "status": {
                            "name": "QA Passed",
                            "statusCategory": {"key": "Done"},
                        }
                    },
                }
            ]
        )
    )

    assert result.tickets[0].status == "QA Passed"
    assert result.tickets[0].status_category == "done"


def test_timestamp_uses_resolution_date_not_last_update_for_open_issues() -> None:
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "DS3-OPEN",
                    "fields": {
                        "status": {"name": "In Progress"},
                        "statuscategorychangedate": "2026-11-02T10:00:00.000+0000",
                        "updated": "2026-11-02T11:00:00.000+0000",
                        "created": "2026-11-01T09:00:00.000+0000",
                    },
                },
                {
                    "key": "DS3-DONE",
                    "fields": {
                        "status": {"name": "Done"},
                        "resolutiondate": "2026-11-02T12:00:00.000+0000",
                        "updated": "2026-11-03T11:00:00.000+0000",
                    },
                },
            ]
        )
    )

    tickets = {ticket.ticket_id: ticket for ticket in result.tickets}
    assert tickets["DS3-OPEN"].timestamp is None
    assert tickets["DS3-DONE"].timestamp == datetime.fromisoformat("2026-11-02T12:00:00+00:00")


def test_normalizes_sprint_dates_and_changelog_history() -> None:
    data = envelope(
        [
            {
                "key": "DS3-4",
                "fields": {
                    "customfield_10020": [
                        {
                            "id": 1,
                            "name": "Sprint 2",
                            "startDate": "2026-11-02T00:00:00.000Z",
                            "endDate": "2026-11-16T00:00:00.000Z",
                        }
                    ],
                    "status": {"name": "Done"},
                    "customfield_10016": 3,
                },
                "changelog": {
                    "histories": [
                        {
                            "created": "2026-11-05T14:00:00.000+0000",
                            "items": [
                                {
                                    "field": "status",
                                    "fieldId": "status",
                                    "fromString": "In Progress",
                                    "toString": "Done",
                                }
                            ],
                        }
                    ]
                },
            }
        ]
    )
    data["sprint_id"] = "sprint-2"
    data["changelog_captured"] = True

    result = normalize_jira_envelope(data, story_points_field="customfield_10016")

    assert result.sprint_start_date.isoformat() == "2026-11-02"
    assert result.sprint_end_date.isoformat() == "2026-11-16"
    assert result.changelog_captured is True
    change = result.tickets[0].changelog[0]
    assert change.created == datetime.fromisoformat("2026-11-05T14:00:00+00:00")
    assert change.items[0].to_string == "Done"


def test_normalizes_numeric_jira_changelog_timestamps() -> None:
    timestamp = int(datetime(2026, 11, 3, 11, tzinfo=UTC).timestamp())
    data = envelope(
        [
            {
                "key": "DS3-NUMERIC-TIME",
                "fields": {"status": {"name": "Done"}},
                "changelog": {
                    "histories": [
                        {
                            "created": timestamp,
                            "items": [
                                {
                                    "field": "status",
                                    "fieldId": "status",
                                    "fromString": "In Progress",
                                    "toString": "Done",
                                }
                            ],
                        }
                    ]
                },
            }
        ]
    )

    result = normalize_jira_envelope(data)

    assert result.tickets[0].changelog[0].created == datetime(
        2026, 11, 3, 11, tzinfo=UTC
    )


def test_normalizes_jira_issue_created_timestamp() -> None:
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "DS3-CREATED",
                    "fields": {"created": "2026-11-03T11:00:00.000+0000"},
                }
            ]
        )
    )

    assert result.tickets[0].created_at == datetime(2026, 11, 3, 11, tzinfo=UTC)


def test_configured_csv_dates_override_jira_sprint_and_resolution_dates() -> None:
    data = envelope(
        [
            {
                "key": "DS3-CSV",
                "fields": {
                    "customfield_10020": [
                        {
                            "id": 2,
                            "name": "Sprint 2",
                            "startDate": "2026-11-02T00:00:00.000Z",
                            "endDate": "2026-11-16T00:00:00.000Z",
                        }
                    ],
                    "customfield_10050": "2024-10-01",
                    "customfield_10051": "2024-10-14",
                    "customfield_10052": "2024-10-08",
                    "resolutiondate": "2026-11-03T11:00:00.000+0000",
                    "status": {"name": "Done"},
                },
            }
        ]
    )
    data["sprint_id"] = "sprint-2"

    result = normalize_jira_envelope(
        data,
        completion_date_field="customfield_10052",
        sprint_start_date_field="customfield_10050",
        sprint_end_date_field="customfield_10051",
    )

    assert result.sprint_start_date.isoformat() == "2024-10-01"
    assert result.sprint_end_date.isoformat() == "2024-10-14"
    assert result.tickets[0].timestamp == datetime(2024, 10, 8, tzinfo=UTC)


def test_normalizer_excludes_issues_from_other_requested_sprints() -> None:
    data = envelope(
        [
            {
                "key": "DS3-SPRINT-2",
                "fields": {
                    "customfield_10100": [
                        {"id": 2, "name": "Sprint 2"},
                    ],
                    "customfield_10016": 3,
                },
            },
            {
                "key": "DS3-SPRINT-3",
                "fields": {
                    "customfield_10100": [
                        {"id": 3, "name": "Sprint 3"},
                    ],
                    "customfield_10016": 5,
                },
            },
        ]
    )
    data["sprint_id"] = "sprint-2"

    result = normalize_jira_envelope(
        data,
        sprint_field="customfield_10100",
        story_points_field="customfield_10016",
    )

    assert [ticket.ticket_id for ticket in result.tickets] == ["DS3-SPRINT-2"]


def test_rejects_issue_without_key() -> None:
    with pytest.raises(JiraNormalizationError, match="must contain a key"):
        normalize_jira_envelope(envelope([{"fields": {"summary": "Missing key"}}]))


def test_unique_email_match_resolves_student() -> None:
    """A unique email match resolves to the student ID."""
    maps = _member_map("u-student-a", "student.a@sprintsight.edu", "Student A")
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "jira-acct-999",
                            "displayName": "Student A",
                            "emailAddress": "student.a@sprintsight.edu",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    assert result.tickets[0].student_id == "u-student-a"


def test_unique_name_match_resolves_student() -> None:
    """A unique display-name match resolves to the student ID."""
    maps = _member_map("u-student-a", "student.a@sprintsight.edu", "Student A")
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "jira-acct-999",
                            "displayName": "Student A",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    assert result.tickets[0].student_id == "u-student-a"


def test_duplicate_email_returns_null() -> None:
    """Two project members with the same email → null."""
    maps = _member_map("u-student-a", "shared@sprintsight.edu", "Student A")
    maps["ids_by_email"]["shared@sprintsight.edu"].append("u-student-b")
    maps["users_by_id"]["u-student-b"] = UserRecord(
        id="u-student-b",
        email="shared@sprintsight.edu",
        full_name="Student B",
        role=Role.STUDENT,
        hashed_password="x",
        is_active=True,
    )
    maps["project_member_ids"].add("u-student-b")
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "jira-acct-999",
                            "displayName": "Student A",
                            "emailAddress": "shared@sprintsight.edu",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    assert result.tickets[0].student_id is None


def test_duplicate_name_returns_null() -> None:
    """Two project members with the same name → null."""
    maps = _member_map("u-student-a", "a@sprintsight.edu", "John Smith")
    maps["ids_by_name"]["john smith"].append("u-student-b")
    maps["users_by_id"]["u-student-b"] = UserRecord(
        id="u-student-b",
        email="b@sprintsight.edu",
        full_name="John Smith",
        role=Role.STUDENT,
        hashed_password="x",
        is_active=True,
    )
    maps["project_member_ids"].add("u-student-b")
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "jira-acct-999",
                            "displayName": "John Smith",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    assert result.tickets[0].student_id is None


def test_conflicting_email_and_name_returns_null() -> None:
    """Email matches student A, name matches student B → null."""
    maps_a = _member_map("u-student-a", "a@sprintsight.edu", "Student A")
    maps_b = _member_map("u-student-b", "b@sprintsight.edu", "Student B")
    # Merge maps: email of A matches student A, name of B matches student B
    maps = {
        "users_by_id": {**maps_a["users_by_id"], **maps_b["users_by_id"]},
        "ids_by_email": {**maps_a["ids_by_email"], **maps_b["ids_by_email"]},
        "ids_by_name": {**maps_a["ids_by_name"], **maps_b["ids_by_name"]},
        "project_member_ids": {"u-student-a", "u-student-b"},
    }
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "jira-acct-999",
                            "displayName": "Student B",
                            "emailAddress": "a@sprintsight.edu",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    assert result.tickets[0].student_id is None


def test_jira_account_id_ignored() -> None:
    """Jira account ID that matches a student ID string is NOT used."""
    maps = _member_map("u-student-a", "a@sprintsight.edu", "Student A")
    result = normalize_jira_envelope(
        envelope(
            [
                {
                    "key": "PROJ-1",
                    "fields": {
                        "assignee": {
                            "id": "u-student-a",
                            "displayName": "Someone Else",
                            "emailAddress": "someone.else@sprintsight.edu",
                        },
                        "summary": "Implement login",
                    },
                },
            ]
        ),
        story_points_field=None,
        **maps,
    )
    # Jira account ID "u-student-a" is ignored; email "someone.else@..." matches no one
    assert result.tickets[0].student_id is None
