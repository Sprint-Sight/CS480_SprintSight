# All attributes are presumed

from pydantic import BaseModel, Field
from typing import Any, List
from datetime import datetime
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation

class ArtifactBundle(BaseModel):
    team_id: str
    sprint_id: str
    commits: List[CommitInfo] = Field(default_factory=list)
    jira_tickets: List[JiraTicket] = Field(default_factory=list)
    peer_evaluations: List[PeerEvaluation] = Field(default_factory=list)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    instructor_expectations: str = "No instructor guidance provided."

sample_bundle = ArtifactBundle(
    team_id="Team_Alpha",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(
            sha="a1f3c02",
            author="Alice",
            message="Add JWT Auth middleware",
            timestamp=datetime(2026, 8, 10, 9, 15),
            lines_added=150, lines_deleted=10,
            files_changed=[
                FileDiff(filename="auth/middleware.py", change_type="added", lines_added=140, lines_deleted=5),
                FileDiff(filename="auth/config.py", change_type="modified", lines_added=10, lines_deleted=5),
            ],
        )
    ],
    jira_tickets=[
        JiraTicket(ticket_id="AUTH-1", summary="Implement JWT", assignee="Alice", status="Done", issue_type="Story", story_points=3, timestamp=datetime(2026, 8, 10, 9, 30))
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Bob", evaluatee="Alice", rating=5, comments="Alice did an incredible job on Auth!")
    ]
)

