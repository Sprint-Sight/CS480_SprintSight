# All attributes are presumed

from pydantic import BaseModel, Field
from typing import List
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation

class ArtifactBundle(BaseModel):
    team_id: str
    sprint_id: str
    commits: List[CommitInfo] = Field(default_factory=list)
    jira_tickets: List[JiraTicket] = Field(default_factory=list)
    peer_evaluations: List[PeerEvaluation] = Field(default_factory=list)

sample_bundle = ArtifactBundle(
    team_id="Team_Alpha",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(author="Alice", message="Add JWT Auth middleware", lines_added=150, lines_deleted=10)
    ],
    jira_tickets=[
        JiraTicket(ticket_id="AUTH-1", summary="Implement JWT", assignee="Alice", status="Done", story_points=3)
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Bob", evaluatee="Alice", rating=5, comments="Alice did an incredible job on Auth!")
    ]
)

print("SUCCESS! ArtifactBundle schema is valid.")
print(sample_bundle.model_dump_json(indent=2))