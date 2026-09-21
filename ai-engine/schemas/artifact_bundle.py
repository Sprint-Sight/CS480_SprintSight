# All attributes are presumed

from typing import Any

from pydantic import BaseModel, Field

from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation


class ArtifactBundle(BaseModel):
    team_id: str
    sprint_id: str
    commits: list[CommitInfo] = Field(default_factory=list)
    jira_tickets: list[JiraTicket] = Field(default_factory=list)
    peer_evaluations: list[PeerEvaluation] = Field(default_factory=list)
    collaboration_metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    instructor_expectations: str = "No instructor guidance provided."
