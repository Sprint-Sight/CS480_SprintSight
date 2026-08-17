from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation

# # FIXTURE DATA FOR TESTING AND DEMONSTRATION

# The Dream Team (High velocity, good teamwork)
high_performing_team = ArtifactBundle(
    team_id="Team_Alpha",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(author="Alice", message="Add JWT Auth middleware", lines_added=150, lines_deleted=10),
        CommitInfo(author="Bob", message="Write unit tests for auth", lines_added=120, lines_deleted=5)
    ],
    jira_tickets=[
        JiraTicket(ticket_id="AUTH-1", summary="Implement JWT", assignee="Alice", status="Done", story_points=5),
        JiraTicket(ticket_id="AUTH-2", summary="Auth Tests", assignee="Bob", status="Done", story_points=3)
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Bob", evaluatee="Alice", rating=5, comments="Alice crushed it!"),
        PeerEvaluation(evaluator="Alice", evaluatee="Bob", rating=5, comments="Bob's tests caught a tricky bug.")
    ]
)

# 2. The One-Person Show (One student does 99% of the work)
imbalanced_team = ArtifactBundle(
    team_id="Team_Beta",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(author="Charlie", message="Build entire frontend and backend API", lines_added=800, lines_deleted=0),
        CommitInfo(author="Dave", message="Fix typo in readme", lines_added=1, lines_deleted=1)
    ],
    jira_tickets=[
        JiraTicket(ticket_id="UI-1", summary="Build Dashboard", assignee="Charlie", status="Done", story_points=8),
        JiraTicket(ticket_id="UI-2", summary="Update Readme", assignee="Dave", status="To Do", story_points=1)
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Charlie", evaluatee="Dave", rating=2, comments="Dave was free riding."),
        PeerEvaluation(evaluator="Dave", evaluatee="Charlie", rating=5, comments="Charlie did everything.")
    ]
)

# 3. The Struggling Team (Nothing got finished)
struggling_team = ArtifactBundle(
    team_id="Team_Gamma",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(author="Eve", message="Start DB schema", lines_added=20, lines_deleted=0)
    ],
    jira_tickets=[
        JiraTicket(ticket_id="DB-1", summary="Design DB", assignee="Eve", status="In Progress", story_points=5),
        JiraTicket(ticket_id="DB-2", summary="Setup ORM", assignee="Frank", status="To Do", story_points=3)
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Eve", evaluatee="Frank", rating=3, comments="Failed to deploy."),
        PeerEvaluation(evaluator="Frank", evaluatee="Eve", rating=3, comments="Hard sprint, didn't finish much.")
    ]
)

if __name__ == "__main__":
    print("SUCCESS! Fixtures loaded and validated by Pydantic.")
    print(f"Team Alpha (Good) Commits: {len(high_performing_team.commits)}")
    print(f"Team Beta (Imbalanced) Commits: {len(imbalanced_team.commits)}")
    print(f"Team Gamma (Struggling) Commits: {len(struggling_team.commits)}")