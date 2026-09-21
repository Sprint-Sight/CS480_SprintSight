# All attributes are presumed

from pydantic import BaseModel, Field
from typing import Any, List
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation

class ArtifactBundle(BaseModel):
    team_id: str
    sprint_id: str
    commits: List[CommitInfo] = Field(default_factory=list)
    jira_tickets: List[JiraTicket] = Field(default_factory=list)
    peer_evaluations: List[PeerEvaluation] = Field(default_factory=list)
    collaboration_metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    instructor_expectations: str = "No instructor guidance provided."
