from datetime import UTC, datetime

import pytest

from app.repositories.interfaces import JiraIngestionRunRecord
from app.schemas.assessment import (
    JiraCleanedSnapshot,
    JiraIssueChange,
    JiraIssueChangeItem,
    JiraTicket,
)
from app.services.burndownService.service import (
    BurndownDataUnavailableError,
    get_burndown_data,
)


def test_burndown_uses_the_requested_run() -> None:
    run = JiraIngestionRunRecord(
        id="sprint-1-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-1",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="sprint-1.json",
        issue_count=1,
        captured_at=datetime(2026, 11, 2, 23, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="1",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-1",
            captured_at=datetime(2026, 11, 2, tzinfo=UTC),
            sprint_start_date=datetime(2026, 11, 1, tzinfo=UTC).date(),
            sprint_end_date=datetime(2026, 11, 5, tzinfo=UTC).date(),
            changelog_captured=True,
            tickets=[
                JiraTicket(
                    ticket_id="TEST-1",
                    summary="Sprint 1 ticket",
                    story_points=5,
                    status="Done",
                    sprint_id="sprint-1",
                    timestamp=datetime(2026, 11, 2, tzinfo=UTC),
                    changelog=[
                        JiraIssueChange(
                            created=datetime(2026, 11, 2, 12, tzinfo=UTC),
                            items=[
                                JiraIssueChangeItem(
                                    field="status",
                                    field_id="status",
                                    from_string="In Progress",
                                    to_string="Done",
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
    )

    result = get_burndown_data(run=run)

    assert result is not None
    assert result.project_id == "project-1"
    assert result.sprint_id == "sprint-1"
    assert result.total_story_points == 5
    assert result.total_tickets == 1
    assert result.start_date == "2026-11-01"
    assert result.end_date == "2026-11-05"
    assert [point.remaining_points for point in result.daily_points] == [5, 0]
    assert result.daily_points[1].completed_points == 5
    assert len(result.ideal_line) == 5


def test_burndown_keeps_in_progress_story_points_remaining() -> None:
    run = JiraIngestionRunRecord(
        id="active-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-1",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="active.json",
        issue_count=1,
        captured_at=datetime(2026, 11, 3, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="2",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-1",
            captured_at=datetime(2026, 11, 3, tzinfo=UTC),
            sprint_start_date=datetime(2026, 11, 2, tzinfo=UTC).date(),
            sprint_end_date=datetime(2026, 11, 5, tzinfo=UTC).date(),
            changelog_captured=True,
            tickets=[
                JiraTicket(
                    ticket_id="TEST-2",
                    summary="Active ticket",
                    story_points=3,
                    status="In Progress",
                    changelog=[
                        JiraIssueChange(
                            created=datetime(2026, 11, 3, 10, tzinfo=UTC),
                            items=[
                                JiraIssueChangeItem(
                                    field="status",
                                    field_id="status",
                                    from_string="To Do",
                                    to_string="In Progress",
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
    )

    result = get_burndown_data(run=run)

    assert result is not None
    assert [point.remaining_points for point in result.daily_points] == [3, 3]
    assert result.daily_points[1].completed_tickets == 0


def test_burndown_replays_story_point_changes_before_completion() -> None:
    run = JiraIngestionRunRecord(
        id="estimate-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-1",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="estimate.json",
        issue_count=1,
        captured_at=datetime(2026, 11, 4, 23, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="2",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-1",
            captured_at=datetime(2026, 11, 4, 23, tzinfo=UTC),
            sprint_start_date=datetime(2026, 11, 2, tzinfo=UTC).date(),
            sprint_end_date=datetime(2026, 11, 5, tzinfo=UTC).date(),
            story_points_field="customfield_10016",
            changelog_captured=True,
            tickets=[
                JiraTicket(
                    ticket_id="TEST-3",
                    summary="Estimated and completed ticket",
                    story_points=8,
                    status="Done",
                    changelog=[
                        JiraIssueChange(
                            created=datetime(2026, 11, 3, 9, tzinfo=UTC),
                            items=[
                                JiraIssueChangeItem(
                                    field="Story Points",
                                    field_id="customfield_10016",
                                    from_string="5",
                                    to_string="8",
                                ),
                                JiraIssueChangeItem(
                                    field="status",
                                    field_id="status",
                                    from_string="To Do",
                                    to_string="In Progress",
                                ),
                            ],
                        ),
                        JiraIssueChange(
                            created=datetime(2026, 11, 4, 12, tzinfo=UTC),
                            items=[
                                JiraIssueChangeItem(
                                    field="status",
                                    field_id="status",
                                    from_string="In Progress",
                                    to_string="Done",
                                )
                            ],
                        ),
                    ],
                )
            ],
        ),
    )

    result = get_burndown_data(run=run)

    assert result is not None
    assert result.total_story_points == 5
    assert [point.remaining_points for point in result.daily_points] == [5, 8, 0]
    assert result.daily_points[2].completed_points == 8


def test_burndown_requires_changelog_and_sprint_dates() -> None:
    run = JiraIngestionRunRecord(
        id="legacy-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-1",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="legacy.json",
        issue_count=0,
        captured_at=datetime(2026, 11, 3, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="1",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-1",
            captured_at=datetime(2026, 11, 3, tzinfo=UTC),
            tickets=[],
        ),
    )

    with pytest.raises(BurndownDataUnavailableError, match="no captured Jira changelog"):
        get_burndown_data(run=run)
    assert run.cleaned_snapshot is not None
    run.cleaned_snapshot.changelog_captured = True
    with pytest.raises(BurndownDataUnavailableError, match="start/end dates were not found"):
        get_burndown_data(run=run)


def test_burndown_rejects_done_issues_without_completion_evidence() -> None:
    run = JiraIngestionRunRecord(
        id="csv-import-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-1",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="csv-import.json",
        issue_count=1,
        captured_at=datetime(2026, 11, 3, 23, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="2",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-1",
            captured_at=datetime(2026, 11, 3, 23, tzinfo=UTC),
            sprint_start_date=datetime(2026, 11, 2, tzinfo=UTC).date(),
            sprint_end_date=datetime(2026, 11, 16, tzinfo=UTC).date(),
            changelog_captured=True,
            tickets=[
                JiraTicket(
                    ticket_id="TEST-CSV-1",
                    summary="Imported completed issue",
                    story_points=5,
                    status="Done",
                )
            ],
        ),
    )

    with pytest.raises(
        BurndownDataUnavailableError,
        match="without a resolution date or a changelog status transition",
    ):
        get_burndown_data(run=run)


def test_burndown_uses_configured_csv_completion_date_instead_of_import_transition() -> None:
    run = JiraIngestionRunRecord(
        id="csv-history-run",
        course_id="course-1",
        project_id="project-1",
        sprint_id="sprint-2",
        jira_project_key="TEST",
        jql="project = TEST",
        raw_bucket="jira",
        raw_object_key="csv-history.json",
        issue_count=1,
        captured_at=datetime(2026, 11, 3, 23, tzinfo=UTC),
        cleaned_snapshot=JiraCleanedSnapshot(
            normalization_version="2",
            jira_project_key="TEST",
            course_id="course-1",
            project_id="project-1",
            sprint_id="sprint-2",
            captured_at=datetime(2026, 11, 3, 23, tzinfo=UTC),
            sprint_start_date=datetime(2024, 10, 1, tzinfo=UTC).date(),
            sprint_end_date=datetime(2024, 10, 14, tzinfo=UTC).date(),
            completion_date_field="customfield_10052",
            changelog_captured=True,
            tickets=[
                JiraTicket(
                    ticket_id="TEST-CSV-2",
                    summary="Historical imported issue",
                    story_points=5,
                    status="Done",
                    timestamp=datetime(2024, 10, 8, tzinfo=UTC),
                    changelog=[
                        JiraIssueChange(
                            created=datetime(2026, 11, 2, tzinfo=UTC),
                            items=[
                                JiraIssueChangeItem(
                                    field="status",
                                    field_id="status",
                                    from_string="To Do",
                                    to_string="Done",
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
    )

    result = get_burndown_data(run=run)

    assert result is not None
    assert result.total_story_points == 5
    assert result.daily_points[0].remaining_points == 5
    assert result.daily_points[7].date == "2024-10-08"
    assert result.daily_points[7].remaining_points == 0
    assert result.daily_points[7].completed_points == 5
