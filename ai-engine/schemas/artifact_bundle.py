# All attributes are presumed

from typing import Any

from pydantic import BaseModel, Field

from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket


class ArtifactBundle(BaseModel):
    team_id: str
    sprint_id: str
    commits: list[CommitInfo] = Field(default_factory=list)
    jira_tickets: list[JiraTicket] = Field(default_factory=list)
    collaboration_metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    # Faculty/student-uploaded reference material about the project (project
    # brief, requirements doc, design notes). These are BACKGROUND CONTEXT
    # for the LLM about what the team is building — intentionally separate
    # from the `documentation` rubric dimension, which scores documentation
    # produced inside the project itself (README, docs/, code comments). The
    # prompt layer treats this field as context, not as rubric evidence.
    project_context_documents: list[dict[str, Any]] = Field(default_factory=list)
    instructor_expectations: str = "No instructor guidance provided."
