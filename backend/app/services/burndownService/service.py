"""Burndown chart service: reconstructs sprint history from Jira changelogs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.repositories.interfaces import JiraIngestionRunRecord
from app.schemas.assessment import JiraCleanedSnapshot, JiraIssueChange, JiraIssueChangeItem
from app.schemas.jira_burndown import JiraBurndownPoint, JiraBurndownResponse

_DONE_STATUSES = {"closed", "complete", "completed", "done", "resolved"}


class BurndownDataUnavailableError(ValueError):
    """Raised when a run lacks the history or sprint dates needed for a chart."""


@dataclass
class _TicketState:
    story_points: float
    status: str | None
    done_status: str | None = None
    in_sprint: bool = True


def _sprint_identity(value: str | None) -> str:
    normalized = (value or "").strip().casefold()
    match = re.fullmatch(r"sprint[\s_-]*(.+)", normalized)
    if match:
        normalized = match.group(1).strip()
    return re.sub(r"[\s_-]+", "", normalized)


def _sprint_value_matches(value: str | None, sprint_id: str) -> bool:
    if not value:
        return False
    candidates = [value]
    candidates.extend(re.findall(r"(?:id|name)=([^,\]]+)", value))
    candidates.extend(re.split(r"[,;]", value))
    target = _sprint_identity(sprint_id)
    return any(_sprint_identity(candidate) == target for candidate in candidates)


def _change_kind(
    field_id: str | None,
    field: str | None,
    snapshot: JiraCleanedSnapshot,
) -> str | None:
    normalized_field = (field or "").strip().casefold()
    if field_id == "status" or normalized_field == "status":
        return "status"
    if (
        snapshot.story_points_field and field_id == snapshot.story_points_field
    ) or normalized_field in {"story points", "story point"}:
        return "points"
    if field_id == snapshot.sprint_field or normalized_field == "sprint":
        return "sprint"
    return None


def _change_value(value: str | None, fallback: str | None) -> str | None:
    return value if value is not None else fallback


def _point_value(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return 0.0
    try:
        points = float(value)
    except ValueError:
        return None
    return points if points >= 0 else None


def _is_done(status: str | None) -> bool:
    return (status or "").strip().casefold() in _DONE_STATUSES


def _is_done_status(status: str | None, custom_done_status: str | None) -> bool:
    return _is_done(status) or (
        bool(custom_done_status)
        and (status or "").strip().casefold() == custom_done_status.strip().casefold()
    )


def _change_status(
    state: _TicketState,
    change: JiraIssueChange,
    snapshot: JiraCleanedSnapshot,
    *,
    reverse: bool,
) -> None:
    items = reversed(change.items) if reverse else change.items
    for item in items:
        kind = _change_kind(item.field_id, item.field, snapshot)
        before = _change_value(item.from_string, item.from_value)
        after = _change_value(item.to_string, item.to_value)
        selected_value = before if reverse else after

        if kind == "status":
            state.status = selected_value
        elif kind == "points":
            points = _point_value(selected_value)
            if points is not None:
                state.story_points = points
        elif kind == "sprint":
            state.in_sprint = _sprint_value_matches(selected_value, snapshot.sprint_id)


def _ticket_events(
    changes: list[JiraIssueChange],
    created_at: datetime | None,
    resolved_at: datetime | None,
    status: str | None,
    custom_done_status: str | None,
    snapshot: JiraCleanedSnapshot,
) -> list[JiraIssueChange]:
    events = list(changes)
    if (
        resolved_at
        and _is_done_status(status, custom_done_status)
        and snapshot.completion_date_field
    ):
        events = []
        for change in changes:
            items = (
                [
                    item
                    for item in change.items
                    if _change_kind(item.field_id, item.field, snapshot) != "status"
                ]
                if change.created > resolved_at
                else change.items
            )
            if items:
                events.append(change.model_copy(update={"items": items}))
    has_matching_completion = (
        any(
            change.created.date() == resolved_at.date()
            and _change_kind(item.field_id, item.field, snapshot) == "status"
            and _is_done_status(item.to_string or item.to_value, custom_done_status)
            for change in events
            for item in change.items
        )
        if resolved_at
        else False
    )
    if (
        resolved_at
        and _is_done_status(status, custom_done_status)
        and not has_matching_completion
    ):
        events.append(
            JiraIssueChange(
                created=resolved_at,
                items=[
                    JiraIssueChangeItem(
                        field="status",
                        field_id="status",
                        from_string="In Progress",
                        to_string=status,
                    )
                ],
            )
        )
    has_sprint_history = any(
        _change_kind(item.field_id, item.field, snapshot) == "sprint"
        for change in events
        for item in change.items
    )
    if (
        created_at
        and created_at.date() > snapshot.sprint_start_date
        and not has_sprint_history
    ):
        events.append(
            JiraIssueChange(
                created=created_at,
                items=[
                    JiraIssueChangeItem(
                        field="Sprint",
                        field_id=snapshot.sprint_field,
                        to_string=snapshot.sprint_id,
                    )
                ],
            )
        )
    return sorted(events, key=lambda change: change.created)


def _has_completion_evidence(
    changes: list[JiraIssueChange],
    resolved_at: datetime | None,
    status: str | None,
    custom_done_status: str | None,
    snapshot: JiraCleanedSnapshot,
) -> bool:
    if not _is_done_status(status, custom_done_status):
        return True
    if resolved_at is not None:
        return True
    return any(
        _change_kind(item.field_id, item.field, snapshot) == "status"
        and _is_done_status(item.to_string or item.to_value, custom_done_status)
        for change in changes
        for item in change.items
    )


def _state_contribution(state: _TicketState) -> float:
    return (
        state.story_points
        if state.in_sprint and not _is_done_status(state.status, state.done_status)
        else 0.0
    )


def get_burndown_data(
    run: JiraIngestionRunRecord,
) -> JiraBurndownResponse | None:
    """Build daily remaining points from the exact run's Jira changelog."""
    snapshot = run.cleaned_snapshot
    if snapshot is None:
        return None
    if isinstance(snapshot, dict):
        snapshot = JiraCleanedSnapshot.model_validate(snapshot)
    if not snapshot.changelog_captured:
        raise BurndownDataUnavailableError(
            "This run has no captured Jira changelog. "
            "Sync the sprint again before requesting its burndown."
        )
    if snapshot.sprint_start_date is None or snapshot.sprint_end_date is None:
        raise BurndownDataUnavailableError(
            "Jira sprint start/end dates were not found. Check the configured Jira sprint field."
        )
    if snapshot.sprint_start_date > snapshot.sprint_end_date:
        raise BurndownDataUnavailableError("Jira sprint start date is after its end date.")

    tickets = snapshot.tickets
    tickets_without_completion_history = [
        ticket.ticket_id
        for ticket in tickets
        if not _has_completion_evidence(
            ticket.changelog,
            ticket.timestamp,
            ticket.status,
            ticket.status if ticket.status_category == "done" else None,
            snapshot,
        )
    ]
    if tickets_without_completion_history:
        examples = ", ".join(tickets_without_completion_history[:5])
        raise BurndownDataUnavailableError(
            "Jira marks completed issues without a resolution date or a changelog "
            f"status transition, so their completion dates cannot be reconstructed: {examples}."
        )

    tickets_without_story_points = [
        ticket.ticket_id for ticket in tickets if ticket.story_points is None
    ]
    if tickets_without_story_points:
        examples = ", ".join(tickets_without_story_points[:5])
        raise BurndownDataUnavailableError(
            "Jira issues are missing story-point estimates, so the burndown would "
            f"understate the sprint workload: {examples}."
        )

    if not tickets:
        return JiraBurndownResponse(
            project_id=run.project_id,
            course_id=run.course_id,
            sprint_id=run.sprint_id,
            total_story_points=0.0,
            total_tickets=0,
            start_date=snapshot.sprint_start_date.isoformat(),
            end_date=snapshot.sprint_end_date.isoformat(),
            daily_points=[],
            ideal_line=[],
        )

    states: list[_TicketState] = []
    events_by_day: dict[date, list[tuple[int, JiraIssueChange]]] = {}
    for index, ticket in enumerate(tickets):
        state = _TicketState(
            story_points=ticket.story_points or 0.0,
            status=ticket.status,
            done_status=ticket.status if ticket.status_category == "done" else None,
        )
        events = _ticket_events(
            ticket.changelog,
            ticket.created_at,
            ticket.timestamp,
            ticket.status,
            state.done_status,
            snapshot,
        )
        for change in reversed(events):
            if change.created.date() >= snapshot.sprint_start_date:
                _change_status(state, change, snapshot, reverse=True)
        states.append(state)
        for change in events:
            change_day = change.created.date()
            if snapshot.sprint_start_date <= change_day <= run.captured_at.date():
                events_by_day.setdefault(change_day, []).append((index, change))

    total_points = sum(state.story_points for state in states if state.in_sprint)
    total_tickets = sum(1 for state in states if state.in_sprint)
    current_remaining = sum(_state_contribution(state) for state in states)
    observed_end = min(snapshot.sprint_end_date, run.captured_at.date())
    daily_points: list[JiraBurndownPoint] = []

    if observed_end >= snapshot.sprint_start_date:
        day = snapshot.sprint_start_date
        while day <= observed_end:
            completed_tickets = 0
            completed_points = 0.0
            for ticket_index, change in sorted(
                events_by_day.get(day, []), key=lambda item: item[1].created
            ):
                state = states[ticket_index]
                before_remaining = _state_contribution(state)
                was_done = _is_done_status(state.status, state.done_status)
                points_before = state.story_points
                _change_status(state, change, snapshot, reverse=False)
                is_done = _is_done_status(state.status, state.done_status)
                current_remaining += _state_contribution(state) - before_remaining
                if not was_done and is_done and state.in_sprint:
                    completed_tickets += 1
                    completed_points += points_before
                elif was_done and not is_done and state.in_sprint:
                    completed_points -= points_before

            daily_points.append(
                JiraBurndownPoint(
                    date=day.isoformat(),
                    remaining_points=round(max(current_remaining, 0.0), 2),
                    completed_tickets=completed_tickets,
                    completed_points=round(completed_points, 2),
                )
            )
            day += timedelta(days=1)

    total_days = (snapshot.sprint_end_date - snapshot.sprint_start_date).days
    ideal_line = [
        {
            "date": (snapshot.sprint_start_date + timedelta(days=day)).isoformat(),
            "remaining_points": round(
                max(total_points - (total_points * day / total_days), 0.0)
                if total_days
                else (total_points if day == 0 else 0.0),
                2,
            ),
        }
        for day in range(total_days + 1 if total_days else 1)
    ]

    return JiraBurndownResponse(
        project_id=run.project_id,
        course_id=run.course_id,
        sprint_id=run.sprint_id,
        total_story_points=round(total_points, 2),
        total_tickets=total_tickets,
        start_date=snapshot.sprint_start_date.isoformat(),
        end_date=snapshot.sprint_end_date.isoformat(),
        daily_points=daily_points,
        ideal_line=ideal_line,
    )
