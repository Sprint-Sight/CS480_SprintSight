from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class JiraTicket(BaseModel): # Jira real API returns id & key
    ticket_id: str = Field(description="e.g. SPRINT-101")
    summary: str = Field(description="Title of task")
    assignee: str | None = Field(default=None, description="Student assigned")
    status: Literal["To Do", "In Progress", "In Review", "Done", "Blocked"] | None = Field(
        description="Match these exactly to your own Jira board's column names once you set it up"
    )
    timestamp: datetime | None = Field(
        default=None,
        description="When this ticket's current status was last set -- mirrors CommitInfo's timestamp field"
    )
    issue_type: Literal["Bug", "Feature", "Story", "Task", "Epic", "Sub-task"] | None = Field(
        description="Type of Jira ticket"
    )
    story_points: Optional[float] = Field(
        default=None, ge=0,
        description="None means not estimated — that's a planning-quality signal, not a value to guess at"
    )
    sprint_id: Optional[str] = Field(
        default=None,
        description="Sprint this ticket is currently assigned to. None for backlog items not yet pulled into a sprint."
    )

    def __str__(self):
        return f"JiraTicket(ticket_id={self.ticket_id}\n, summary={self.summary}\n, assignee={self.assignee}\n, status={self.status}\n, timestamp={self.timestamp}\n, issue_type={self.issue_type}\n, story_points={self.story_points}\n, sprint_id={self.sprint_id}\n)"

# Different ticket types (epic vs story vs task)

# # SECTION 3 — JIRA / AGILE METRICS

# class JiraTicket(BaseModel):
#     """A single Jira issue in scope for this sprint."""
 
#     ticket_key: str = Field(
#         description=(
#             "Jira issue key (e.g., 'SS-42'). Commit messages referencing ticket keys "
#             "are a positive signal for Requirements traceability."
#         )
#     )
#     summary: str = Field(
#         description=(
#             "Issue title. Used to assess alignment between planned work (backlog) "
#             "and actual deliverables (commits and PRs)."
#         )
#     )
#     assignee_student_id: Optional[str] = Field(
#         default=None,
#         description=(
#             "Assigned student_id. None indicates an unassigned ticket — "
#             "a process health signal, especially for high-priority items."
#         ),
#     )
#     assignee_handle: Optional[str] = Field(
#         default=None,
#         description="Anonymized handle of the assignee for LLM prompt rendering.",
#     )
#     status: Literal["Done", "In Progress", "To Do", "Blocked", "In Review"] = Field(
#         description="Ticket status at sprint end."
#     )
#     story_points: Optional[int] = Field(
#         default=None,
#         ge=0,
#         description=(
#             "Estimated story points. None = not estimated, which is itself a "
#             "planning quality signal for the Requirements dimension."
#         ),
#     )
#     issue_type: Literal["Bug", "Feature", "Story", "Task", "Epic", "Sub-task"] = Field(
#         description=(
#             "Issue type. Bug-type tickets are tracked separately for Code Quality signals. "
#             "A high Bug ratio relative to Feature/Story ratio indicates quality issues."
#         )
#     )
#     priority: Literal["Low", "Medium", "High", "Critical"] = Field(
#         default="Medium",
#         description=(
#             "Ticket priority. Incomplete High or Critical tickets carry more weight "
#             "in the Requirements dimension than incomplete Low tickets."
#         ),
#     )
#     sprint_id: str = Field(
#         description="Sprint this ticket belongs to (tickets can span sprints as spillover)."
#     )
#     created_date: Optional[date] = Field(
#         default=None,
#         description=(
#             "Ticket creation date. Tickets created during the sprint (not pre-planned) "
#             "may indicate scope creep or reactive rather than proactive planning."
#         ),
#     )
#     resolved_date: Optional[date] = Field(
#         default=None,
#         description="Date the ticket was moved to Done. None if not completed.",
#     )
#     labels: list[str] = Field(
#         default_factory=list,
#         description="Applied Jira labels for categorisation (e.g., 'backend', 'blocked-by-PR').",
#     )
 
 
# class JiraMetrics(BaseModel):
#     """Sprint-level Jira analytics and raw ticket data."""
 
#     velocity_target_points: int = Field(
#         ge=0,
#         description=(
#             "Total story points committed at sprint planning. "
#             "Represents the team's self-assessed workload capacity."
#         ),
#     )
#     velocity_completed_points: int = Field(
#         ge=0,
#         description=(
#             "Story points from tickets with final status 'Done' at sprint end. "
#             "Velocity ratio = completed / target. Ratio < 0.6 is a planning concern."
#         ),
#     )
#     tickets: list[JiraTicket] = Field(
#         default_factory=list,
#         description="All tickets in scope for this sprint, including spillover from prior sprints.",
#     )
#     bugs_introduced: int = Field(
#         default=0,
#         ge=0,
#         description=(
#             "Bug-type tickets created during this sprint, indicating newly discovered defects. "
#             "High values relative to features delivered signal code quality issues."
#         ),
#     )
#     bugs_resolved: int = Field(
#         default=0,
#         ge=0,
#         description="Bug tickets moved to Done during this sprint.",
#     )
 
#     @property
#     def velocity_ratio(self) -> float:
#         if self.velocity_target_points == 0:
#             return 0.0
#         return round(self.velocity_completed_points / self.velocity_target_points, 3)
 
#     @property
#     def incomplete_tickets(self) -> list[JiraTicket]:
#         return [t for t in self.tickets if t.status != "Done"]
 
#     @property
#     def tickets_by_type(self) -> dict[str, int]:
#         result: dict[str, int] = {}
#         for t in self.tickets:
#             result[t.issue_type] = result.get(t.issue_type, 0) + 1
#         return result
 
#     @property
#     def completion_rate_by_student(self) -> dict[str, dict]:
#         """Per-student assigned vs completed story points."""
#         result: dict[str, dict] = {}
#         for ticket in self.tickets:
#             if not ticket.assignee_student_id:
#                 continue
#             sid = ticket.assignee_student_id
#             if sid not in result:
#                 result[sid] = {"assigned": 0, "completed": 0, "ticket_count": 0}
#             pts = ticket.story_points or 0
#             result[sid]["assigned"] += pts
#             result[sid]["ticket_count"] += 1
#             if ticket.status == "Done":
#                 result[sid]["completed"] += pts
#         return result