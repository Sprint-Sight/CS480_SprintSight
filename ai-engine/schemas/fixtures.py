from datetime import UTC, datetime

from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation

# The Best Team (Good performance, good work distribution among team members)
high_performing_team = ArtifactBundle(
    team_id="Team_Alpha",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(
            sha="a1f3c02",
            author="Alice",
            message="Add JWT Auth middleware",
            timestamp=datetime(2026, 8, 10, 9, 15, tzinfo=UTC),
            lines_added=150,
            lines_deleted=10,
            files_changed=[
                FileDiff(filename="auth/middleware.py", change_type="added", lines_added=140, lines_deleted=5),
                FileDiff(filename="auth/config.py", change_type="modified", lines_added=10, lines_deleted=5),
            ],
        ),
        CommitInfo(
            sha="b2g4d13",
            author="Bob",
            message="Write unit tests for auth",
            timestamp=datetime(2026, 8, 10, 10, 30, tzinfo=UTC),
            lines_added=120,
            lines_deleted=5,
            files_changed=[
                FileDiff(filename="tests/test_auth.py", change_type="added", lines_added=120, lines_deleted=5),
            ],
        ),
        CommitInfo(
            sha="c3h5e24",
            author="Charlie",
            message="Refactor auth service for performance",
            timestamp=datetime(2026, 8, 10, 11, 45, tzinfo=UTC),
            lines_added=80,
            lines_deleted=20,
            files_changed=[
                FileDiff(filename="auth/service.py", change_type="modified", lines_added=80, lines_deleted=20),
            ],
        ),
        CommitInfo(
            sha="d4i6f35",
            author="Alice",
            message="Fix bug in auth token refresh",
            timestamp=datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
            lines_added=30,
            lines_deleted=2,
            files_changed=[
                FileDiff(filename="auth/middleware.py", change_type="modified", lines_added=30, lines_deleted=2),
            ],
        ),
        CommitInfo(
            sha="e5j7g46",
            author="Bob",
            message="Update auth documentation",
            timestamp=datetime(2026, 8, 10, 14, 15, tzinfo=UTC),
            lines_added=50,
            lines_deleted=0,
            files_changed=[
                FileDiff(filename="docs/auth.md", change_type="modified", lines_added=50, lines_deleted=0),
            ],
        ),
        CommitInfo(
            sha="f6k8h57",
            author="Charlie",
            message="Implement auth logging",
            timestamp=datetime(2026, 8, 10, 15, 30, tzinfo=UTC),
            lines_added=60,
            lines_deleted=5,
            files_changed=[
                FileDiff(filename="auth/logging.py", change_type="added", lines_added=60, lines_deleted=5),
            ],
        )

    ],
    jira_tickets=[
        JiraTicket(ticket_id="AUTH-1", summary="Implement JWT", assignee="Alice", status="Done", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 10, 9, 30, tzinfo=UTC)),
        JiraTicket(ticket_id="AUTH-2", summary="Auth Tests", assignee="Bob", status="Done", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 10, 10, 45, tzinfo=UTC)),
        JiraTicket(ticket_id="AUTH-3", summary="Refactor Auth Service", assignee="Charlie", status="Done", issue_type="Task", story_points=5, timestamp=datetime(2026, 8, 10, 12, 0, tzinfo=UTC)),
        JiraTicket(ticket_id="AUTH-4", summary="Auth Bug Fix", assignee="Alice", status="Done", issue_type="Bug", story_points=2, timestamp=datetime(2026, 8, 10, 13, 15, tzinfo=UTC)),
        JiraTicket(ticket_id="AUTH-5", summary="Auth Documentation", assignee="Bob", status="Done", issue_type="Task", story_points=1, timestamp=datetime(2026, 8, 10, 14, 30, tzinfo=UTC)),
        JiraTicket(ticket_id="AUTH-6", summary="Auth Logging", assignee="Charlie", status="Done", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 10, 15, 45, tzinfo=UTC)),
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Bob", evaluatee="Alice", rating=5, comments="Alice crushed it!"),
        PeerEvaluation(evaluator="Alice", evaluatee="Bob", rating=5, comments="Bob's tests caught a tricky bug."),
        PeerEvaluation(evaluator="Charlie", evaluatee="Alice", rating=5, comments="Alice's refactor improved performance significantly."),
        PeerEvaluation(evaluator="Alice", evaluatee="Charlie", rating=5, comments="Charlie's logging implementation is top-notch."),
        PeerEvaluation(evaluator="Bob", evaluatee="Charlie", rating=5, comments="Charlie refactored the auth service beautifully."),
        PeerEvaluation(evaluator="Charlie", evaluatee="Bob", rating=5, comments="Bob's documentation updates were clear and helpful."),
    ]
)

# The Struggling Team (Nil / little work done)
struggling_team = ArtifactBundle(
    team_id="Team_Gamma",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(sha="9f8e7d6", author="Greg", message="Start DB schema", timestamp=datetime(2026, 8, 10, 10, 0, tzinfo=UTC), lines_added=20, lines_deleted=0,
            files_changed=[FileDiff(filename="db/schema.py", change_type="added", lines_added=20, lines_deleted=0)]),
        CommitInfo(sha="8e7d6c5", author="Frank", message="Attempt to implement API", timestamp=datetime(2026, 8, 12, 15, 20, tzinfo=UTC), lines_added=30, lines_deleted=5,
            files_changed=[FileDiff(filename="api/routes.py", change_type="added", lines_added=30, lines_deleted=5)]),
        CommitInfo(sha="7d6c5b4", author="Hank", message="Write some tests", timestamp=datetime(2026, 8, 14, 9, 40, tzinfo=UTC), lines_added=10, lines_deleted=0,
            files_changed=[FileDiff(filename="tests/test_db.py", change_type="added", lines_added=10, lines_deleted=0)]),
        CommitInfo(sha="6c5b4a3", author="Greg", message="Fix DB schema", timestamp=datetime(2026, 8, 17, 11, 15, tzinfo=UTC), lines_added=5, lines_deleted=2,
            files_changed=[FileDiff(filename="db/schema.py", change_type="modified", lines_added=5, lines_deleted=2)]),
        CommitInfo(sha="5b4a392", author="Frank", message="Refactor API", timestamp=datetime(2026, 8, 19, 14, 0, tzinfo=UTC), lines_added=5, lines_deleted=1,
            files_changed=[FileDiff(filename="api/routes.py", change_type="modified", lines_added=5, lines_deleted=1)]),
        CommitInfo(sha="4a39281", author="Hank", message="Update tests", timestamp=datetime(2026, 8, 20, 16, 30, tzinfo=UTC), lines_added=2, lines_deleted=0,
            files_changed=[FileDiff(filename="tests/test_db.py", change_type="modified", lines_added=2, lines_deleted=0)]),
    ],
    jira_tickets=[
        JiraTicket(ticket_id="DB-1", summary="Design DB", assignee="Greg", status="In Progress", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 10, 10, 0, tzinfo=UTC)),
        JiraTicket(ticket_id="DB-2", summary="Setup ORM", assignee="Frank", status="To Do", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 10, 9, 0, tzinfo=UTC)),
        JiraTicket(ticket_id="DB-3", summary="Write DB Tests", assignee="Hank", status="To Do", issue_type="Task", story_points=2, timestamp=datetime(2026, 8, 10, 9, 0, tzinfo=UTC)),
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Greg", evaluatee="Frank", rating=3, comments="Frank was slow to respond."),
        PeerEvaluation(evaluator="Frank", evaluatee="Greg", rating=3, comments="Greg tried his best but struggled to get task done"),
        PeerEvaluation(evaluator="Hank", evaluatee="Greg", rating=2, comments="Greg didn't contribute much."),
        PeerEvaluation(evaluator="Hank", evaluatee="Frank", rating=2, comments="Frank was not helpful."),
        PeerEvaluation(evaluator="Greg", evaluatee="Hank", rating=3, comments="Hank was not proactive."),
        PeerEvaluation(evaluator="Frank", evaluatee="Hank", rating=3, comments="Hank did the bare minimum."),
    ]
)

# Good collaboration, lower output
good_collab_low_output_team = ArtifactBundle(
    team_id="Team_Delta",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(sha="d1e2f3a", author="Ivy", message="Add login page skeleton", timestamp=datetime(2026, 8, 11, 10, 0, tzinfo=UTC), lines_added=35, lines_deleted=2,
            files_changed=[FileDiff(filename="auth/login_page.py", change_type="added", lines_added=35, lines_deleted=2)]),
        CommitInfo(sha="d2e3f4b", author="Jack", message="Style navbar component", timestamp=datetime(2026, 8, 13, 14, 20, tzinfo=UTC), lines_added=25, lines_deleted=1,
            files_changed=[FileDiff(filename="components/navbar.css", change_type="modified", lines_added=25, lines_deleted=1)]),
        CommitInfo(sha="d3e4f5c", author="Kim", message="Add basic form validation", timestamp=datetime(2026, 8, 15, 11, 30, tzinfo=UTC), lines_added=40, lines_deleted=5,
            files_changed=[FileDiff(filename="forms/validation.py", change_type="added", lines_added=40, lines_deleted=5)]),
        CommitInfo(sha="d4e5f6d", author="Ivy", message="Fix navbar responsiveness", timestamp=datetime(2026, 8, 18, 9, 45, tzinfo=UTC), lines_added=20, lines_deleted=3,
            files_changed=[FileDiff(filename="components/navbar.css", change_type="modified", lines_added=20, lines_deleted=3)]),
    ],
    jira_tickets=[
        JiraTicket(ticket_id="DEL-1", summary="Build login page", assignee="Ivy", status="Done", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 11, 10, 15, tzinfo=UTC)),
        JiraTicket(ticket_id="DEL-2", summary="Style navbar", assignee="Jack", status="Done", issue_type="Task", story_points=2, timestamp=datetime(2026, 8, 13, 14, 35, tzinfo=UTC)),
        JiraTicket(ticket_id="DEL-3", summary="Add form validation", assignee="Kim", status="In Progress", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 15, 11, 30, tzinfo=UTC)),
        JiraTicket(ticket_id="DEL-4", summary="Responsive layout pass", assignee="Ivy", status="To Do", issue_type="Task", story_points=2, timestamp=datetime(2026, 8, 10, 9, 0, tzinfo=UTC)),
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Ivy", evaluatee="Jack", rating=5, comments="Jack's navbar work looks great and he's always quick to help."),
        PeerEvaluation(evaluator="Ivy", evaluatee="Kim", rating=4, comments="Kim communicates clearly about blockers."),
        PeerEvaluation(evaluator="Jack", evaluatee="Ivy", rating=5, comments="Ivy keeps the team organized and unblocks people fast."),
        PeerEvaluation(evaluator="Jack", evaluatee="Kim", rating=4, comments="Kim is thorough, just a bit slow to start tasks."),
        PeerEvaluation(evaluator="Kim", evaluatee="Ivy", rating=5, comments="Ivy is a great communicator and very supportive."),
        PeerEvaluation(evaluator="Kim", evaluatee="Jack", rating=4, comments="Jack is reliable and easy to work with."),
    ]
)

# 1 person carry, good outcome
imbalanced_high_output_team = ArtifactBundle(
    team_id="Team_Epsilon",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(sha="e1a2b3c", author="Liam", message="Build payment processing service", timestamp=datetime(2026, 8, 10, 8, 30, tzinfo=UTC), lines_added=280, lines_deleted=15,
            files_changed=[
                FileDiff(filename="payments/service.py", change_type="added", lines_added=250, lines_deleted=10),
                FileDiff(filename="payments/models.py", change_type="added", lines_added=30, lines_deleted=5),
            ]),
        CommitInfo(sha="e2b3c4d", author="Liam", message="Add payment webhook handlers", timestamp=datetime(2026, 8, 13, 13, 15, tzinfo=UTC), lines_added=190, lines_deleted=8,
            files_changed=[FileDiff(filename="payments/webhooks.py", change_type="added", lines_added=190, lines_deleted=8)]),
        CommitInfo(sha="e3c4d5e", author="Liam", message="Implement refund flow", timestamp=datetime(2026, 8, 16, 10, 0, tzinfo=UTC), lines_added=160, lines_deleted=10,
            files_changed=[FileDiff(filename="payments/refunds.py", change_type="added", lines_added=160, lines_deleted=10)]),
        CommitInfo(sha="e4d5e6f", author="Liam", message="Add payment audit logging", timestamp=datetime(2026, 8, 19, 15, 40, tzinfo=UTC), lines_added=150, lines_deleted=5,
            files_changed=[FileDiff(filename="payments/audit_log.py", change_type="added", lines_added=150, lines_deleted=5)]),
        CommitInfo(sha="e5e6f7a", author="Maya", message="Fix typo in payment config comment", timestamp=datetime(2026, 8, 20, 9, 0, tzinfo=UTC), lines_added=1, lines_deleted=1,
            files_changed=[FileDiff(filename="payments/config.py", change_type="modified", lines_added=1, lines_deleted=1)]),
        CommitInfo(sha="e6f7a8b", author="Noah", message="Update .gitignore", timestamp=datetime(2026, 8, 20, 9, 30, tzinfo=UTC), lines_added=2, lines_deleted=0,
            files_changed=[FileDiff(filename=".gitignore", change_type="modified", lines_added=2, lines_deleted=0)]),
    ],
    jira_tickets=[
        JiraTicket(ticket_id="PAY-1", summary="Build payment processing service", assignee="Liam", status="Done", issue_type="Story", story_points=8, timestamp=datetime(2026, 8, 10, 8, 45, tzinfo=UTC)),
        JiraTicket(ticket_id="PAY-2", summary="Payment webhook handlers", assignee="Liam", status="Done", issue_type="Task", story_points=5, timestamp=datetime(2026, 8, 13, 13, 30, tzinfo=UTC)),
        JiraTicket(ticket_id="PAY-3", summary="Implement refund flow", assignee="Liam", status="Done", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 16, 10, 15, tzinfo=UTC)),
        JiraTicket(ticket_id="PAY-4", summary="Payment audit logging", assignee="Liam", status="Done", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 19, 15, 55, tzinfo=UTC)),
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Maya", evaluatee="Liam", rating=5, comments="Liam carried the entire payments module practically by himself."),
        PeerEvaluation(evaluator="Noah", evaluatee="Liam", rating=5, comments="Liam shipped all four payment tickets alone, incredible pace."),
        PeerEvaluation(evaluator="Liam", evaluatee="Maya", rating=2, comments="Maya didn't pick up any tickets this sprint, I had to step in."),
        PeerEvaluation(evaluator="Liam", evaluatee="Noah", rating=2, comments="Noah only made a one-line config fix all sprint, hence I had to do the rest."),
    ]
)

# Only 1 person did any work, and the outcome was still poor
lone_contributor_poor_outcome_team = ArtifactBundle(
    team_id="Team_Theta",
    sprint_id="Sprint_1",
    commits=[
        CommitInfo(sha="b1a2b3c", author="Uma", message="Start report generation feature", timestamp=datetime(2026, 8, 12, 20, 0, tzinfo=UTC), lines_added=25, lines_deleted=2,
            files_changed=[FileDiff(filename="reports/generator.py", change_type="added", lines_added=25, lines_deleted=2)]),
        CommitInfo(sha="b2b3c4d", author="Uma", message="WIP, ran out of time", timestamp=datetime(2026, 8, 17, 23, 30, tzinfo=UTC), lines_added=18, lines_deleted=4,
            files_changed=[FileDiff(filename="reports/export.py", change_type="modified", lines_added=18, lines_deleted=4)]),
        CommitInfo(sha="b3c4d5e", author="Uma", message="Partial fix for report export bug", timestamp=datetime(2026, 8, 20, 22, 10, tzinfo=UTC), lines_added=15, lines_deleted=3,
            files_changed=[FileDiff(filename="reports/export.py", change_type="modified", lines_added=15, lines_deleted=3)]),
    ],
    jira_tickets=[
        JiraTicket(ticket_id="REP-1", summary="Build report generation core", assignee="Uma", status="Done", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 12, 20, 15, tzinfo=UTC)),
        JiraTicket(ticket_id="REP-2", summary="Add report export (PDF/CSV)", assignee="Uma", status="In Progress", issue_type="Story", story_points=5, timestamp=datetime(2026, 8, 17, 23, 30, tzinfo=UTC)),
        JiraTicket(ticket_id="REP-3", summary="Add report scheduling", assignee="Uma", status="To Do", issue_type="Task", story_points=3, timestamp=datetime(2026, 8, 10, 9, 0, tzinfo=UTC)),
        JiraTicket(ticket_id="REP-4", summary="Add report access permissions", assignee="Uma", status="To Do", issue_type="Task", story_points=2, timestamp=datetime(2026, 8, 10, 9, 0, tzinfo=UTC)),
    ],
    peer_evaluations=[
        PeerEvaluation(evaluator="Uma", evaluatee="Victor", rating=1, comments="Victor did not contribute to any report tickets."),
        PeerEvaluation(evaluator="Uma", evaluatee="Wei", rating=2, comments="Wei helped plan but wrote no code."),
        PeerEvaluation(evaluator="Victor", evaluatee="Uma", rating=4, comments="Uma tried hard but we still missed most of our sprint goals."),
        PeerEvaluation(evaluator="Wei", evaluatee="Uma", rating=3, comments="Uma carried the whole feature alone and it was too much for one person."),
    ]
)

if __name__ == "__main__":
    pass