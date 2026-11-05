"""Schemas for Jira burndown chart reporting."""

from pydantic import BaseModel, Field


class JiraBurndownPoint(BaseModel):
    """A single data point on a burndown chart."""

    date: str = Field(..., description="ISO date string (YYYY-MM-DD).")
    remaining_points: float = Field(
        ..., description="Remaining story points at end of day."
    )
    completed_tickets: int = Field(
        default=0, description="Number of tickets completed on this day."
    )
    completed_points: float = Field(
        default=0.0, description="Story points completed on this day."
    )


class JiraBurndownResponse(BaseModel):
    """Burndown chart data for a project sprint."""

    project_id: str = Field(..., description="SprintSight project ID.")
    course_id: str = Field(..., description="Course ID.")
    sprint_id: str | None = Field(
        default=None, description="Sprint identifier."
    )
    total_story_points: float = Field(
        default=0.0, description="Total story points at sprint start."
    )
    total_tickets: int = Field(
        default=0, description="Total number of tickets."
    )
    start_date: str | None = Field(
        default=None,
        description="Sprint start date (first ticket date or sprint start).",
    )
    end_date: str | None = Field(
        default=None,
        description="Sprint end date (last ticket date or sprint end).",
    )
    daily_points: list[JiraBurndownPoint] = Field(
        default_factory=list,
        description="Daily remaining points (one entry per day with activity).",
    )
    ideal_line: list[dict[str, object]] = Field(
        default_factory=list,
        description="Ideal burndown line: [{date, remaining_points}, ...].",
    )
