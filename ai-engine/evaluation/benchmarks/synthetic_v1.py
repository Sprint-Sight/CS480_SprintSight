"""Synthetic benchmark set v1: five hand-written teams and their gold assessments.

Bundles (formerly schemas/fixtures.py), gold (formerly schemas/benchmark.py) and the
FIXTURES key -> bundle map (formerly schemas/benchmark_registry.py) in one module.

Used offline: the d1_fixtures dataset, the judge study's gold_by_fixture and the validation
harness. Not the same data as synthetic_v2 although the team_ids match: v1 uses sprint
"Sprint_1" and short hand-written SHAs.
"""

from datetime import UTC, datetime

from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.member_contribution import MemberContribution
from schemas.peer_evaluation import PeerEvaluation
from schemas.rubrics_dimension_score import (
    ResolvedEvidenceCitation,
    RubricDimensionScore,
)
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment

# =============================================================================
# Bundles
# =============================================================================

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

# Fixture key -> bundle, so callers that only receive plain JSON-able inputs (e.g. an MLflow
# scorer) can look up which bundle produced an assessment. Keys match
# research/trials/validation_harness.py's FIXTURE_CANDIDATES and the gold below.
FIXTURES: dict[str, ArtifactBundle] = {
    "high_performing": high_performing_team,
    "struggling": struggling_team,
    "good_collab_low_output": good_collab_low_output_team,
    "imbalanced_high_output": imbalanced_high_output_team,
    "lone_contributor_poor_outcome": lone_contributor_poor_outcome_team,
}


# =============================================================================
# Gold assessments
# =============================================================================

def _cite(text: str) -> ResolvedEvidenceCitation:
    """Wrap a hand-authored benchmark citation sentence as an EvidenceCitation --
    reused for both `identifier` and `reason` since these gold citations are
    already full sentences, not the (identifier, reason) pairs a real model
    produces."""
    return ResolvedEvidenceCitation(identifier=text, reason=text)


high_performing_grade = SprintAssessment(
    team_id=high_performing_team.team_id,
    sprint_id=high_performing_team.sprint_id,
    prompt_version="v1.0",
    overall_score=7.5,  # mean of all 6 dimensions: (9+8+8+9+10+1)/6
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=9,
            justification="Commits are small and single-purpose across all three members, with no large untested diffs.",
            evidence_citations=[
                _cite("Charlie's 'Refactor auth service for performance' commit is a focused +80/-20 change."),
                _cite("Alice's 'Fix bug in auth token refresh' commit is a targeted +30/-2 fix."),
            ],
            strengths=["Small, focused commits", "Clear one-concern-per-commit pattern"],
            areas_for_improvement=["Commit messages don't reference Jira ticket IDs directly"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=8,
            justification="A dedicated testing ticket was completed alongside the feature it covers.",
            evidence_citations=[
                _cite("Jira ticket AUTH-2 'Auth Tests' is marked Done, assigned to Bob."),
                _cite("Bob's 'Write unit tests for auth' commit added 120 lines to the new tests/test_auth.py."),
            ],
            strengths=["Testing tracked as its own ticket, not an afterthought"],
            areas_for_improvement=["No coverage percentage is visible from the artifacts"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=8,
            justification="Documentation was planned and delivered as its own ticket.",
            evidence_citations=[
                _cite("Jira ticket AUTH-5 'Auth Documentation' is marked Done."),
                _cite("Bob's 'Update auth documentation' commit added 50 lines to docs/auth.md."),
            ],
            strengths=["Documentation given its own ticket and commit"],
            areas_for_improvement=["No README or architecture diagram referenced in the artifacts"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=9,
            justification="All 6 planned Jira tickets for the sprint are marked Done.",
            evidence_citations=[
                _cite("Jira tickets AUTH-1 through AUTH-6 are all marked Done."),
                _cite("19 story points were planned and fully delivered."),
            ],
            strengths=["100% ticket completion for the sprint"],
            areas_for_improvement=["Story point estimates aren't validated against actual effort"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=10,
            justification="All 6 peer evaluations gave the maximum rating with specific, substantive comments.",
            evidence_citations=[
                _cite("Bob rated Alice 5/5: 'Alice crushed it!'"),
                _cite("Charlie rated Bob 5/5: 'Bob's documentation updates were clear and helpful.'"),
            ],
            strengths=["Every teammate gave specific, positive feedback about a teammate"],
            areas_for_improvement=["No constructive critique appears anywhere in peer feedback"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd",
            score=1,
            justification="No CI/CD artifact exists in this sprint: no workflow or pipeline configuration, no Dockerfile, and artifact_metrics is empty. Band 1-2 applies.",
            evidence_citations=[
                _cite("Commits a1f3c02 through d4i6f35 touch only auth/service.py, tests/test_auth.py and docs/auth.md; no pipeline or workflow file appears in any of the 6 commits."),
                _cite("Tickets AUTH-1 through AUTH-6 cover middleware, tests, documentation and logging; none plans CI, build or deployment work."),
            ],
            strengths=[],
            areas_for_improvement=["Add a CI workflow that runs the existing tests/test_auth.py suite on every push", "No automated deployment or build step exists to attribute to any member"],
        ),
    ),
    member_contributions=[
        MemberContribution(
            student_id="Alice", contribution_score=9,
            primary_contributions=["Implemented JWT Auth middleware (AUTH-1)", "Fixed auth token refresh bug (AUTH-4)"],
            evidence=["Commit 'Add JWT Auth middleware' (+150/-10)", "Jira AUTH-1 and AUTH-4 both marked Done"],
        ),
        MemberContribution(
            student_id="Bob", contribution_score=9,
            primary_contributions=["Wrote unit tests for auth (AUTH-2)", "Authored auth documentation (AUTH-5)"],
            evidence=["Commit 'Write unit tests for auth' (+120/-5)", "Jira AUTH-2 and AUTH-5 marked Done"],
        ),
        MemberContribution(
            student_id="Charlie", contribution_score=8,
            primary_contributions=["Refactored auth service for performance (AUTH-3)", "Implemented auth logging (AUTH-6)"],
            evidence=["Commit 'Refactor auth service for performance' (+80/-20)", "Jira AUTH-3 and AUTH-6 marked Done"],
        ),
    ],
    executive_summary="Team_Alpha delivered all 6 planned Jira tickets this sprint with consistently strong code quality and universally positive peer feedback across all three members.",
    key_recommendations=[
        "Reference Jira ticket IDs in commit messages for traceability.",
        "Add code coverage reporting to substantiate testing quality.",
    ],
)

struggling_grade = SprintAssessment(
    team_id=struggling_team.team_id,
    sprint_id=struggling_team.sprint_id,
    prompt_version="v1.0",
    overall_score=2.67,  # mean of all 6 dimensions: (5+2+2+2+4+1)/6
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=5,
            justification="Commits are small and iterative, and one message signals outright uncertainty about the approach.",
            evidence_citations=[
                _cite("Frank's commit message 'Attempt to implement API' signals low confidence in the implementation."),
                _cite("No commit in this sprint exceeds 30 lines, indicating slow, tentative progress."),
            ],
            strengths=["The team iterated on issues (e.g. 'Fix DB schema') rather than abandoning the code"],
            areas_for_improvement=["Commit messages suggest the team is unsure whether its approach works", "Progress is slow relative to sprint length"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=2,
            justification="Some testing activity occurred but the dedicated testing ticket was never closed.",
            evidence_citations=[
                _cite("Jira ticket DB-3 'Write DB Tests' is still marked To Do despite two related commits."),
                _cite("Hank's testing commits total only 12 lines across the sprint."),
            ],
            strengths=["Testing work was started even though the ticket wasn't formally closed"],
            areas_for_improvement=["The dedicated testing ticket (DB-3) was never marked Done", "Test coverage appears minimal given only 12 lines of test code"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=2,
            justification="No documentation work was planned or delivered this sprint.",
            evidence_citations=[
                _cite("No Jira ticket in this sprint addresses documentation."),
                _cite("None of the 6 commits touch a docs/ or README file — all changes are to db/schema.py, api/routes.py, or tests/test_db.py."),
            ],
            strengths=["Commit messages, while terse, do describe what each change does"],
            areas_for_improvement=["No documentation work exists for the DB schema design, the sprint's main focus"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=2,
            justification="Zero of the 3 planned tickets reached Done status by sprint end.",
            evidence_citations=[
                _cite("None of the 3 planned Jira tickets (DB-1, DB-2, DB-3) reached Done status."),
                _cite("DB-1 'Design DB' is still In Progress despite two related commits from Greg."),
            ],
            strengths=["DB-1 did progress from not-started to In Progress"],
            areas_for_improvement=["Zero of 3 planned tickets were completed", "All 10 planned story points remain undelivered"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=4,
            justification="Peer feedback is uniformly mediocre across all three members, indicating broad underperformance rather than one blocker.",
            evidence_citations=[
                _cite("All 6 peer evaluations this sprint rate teammates 2 or 3 out of 5, with no rating above 3."),
                _cite("Hank rated Greg 2/5 ('Greg didn't contribute much') while Greg rated Hank 3/5 ('Hank was not proactive')."),
            ],
            strengths=["Feedback, while critical, is specific rather than hostile"],
            areas_for_improvement=["No team member received a rating above 3/5 from any peer", "The team should discuss blockers directly rather than only surfacing them in peer evaluations"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd",
            score=1,
            justification="No CI/CD artifact exists in this sprint: no workflow or pipeline configuration, no Dockerfile, and artifact_metrics is empty. Band 1-2 applies.",
            evidence_citations=[
                _cite("Commit 9f8e7d6 and the other 5 commits touch only api/routes.py, db/schema.py and tests/test_db.py; no pipeline or workflow file is present."),
                _cite("Tickets DB-1, DB-2 and DB-3 cover schema and API work only; none plans CI, build or deployment work."),
            ],
            strengths=[],
            areas_for_improvement=["Add a CI workflow that runs tests/test_db.py so the failing database work is caught automatically", "No automated build or deployment step exists to attribute to any member"],
        ),
    ),
    member_contributions=[
        MemberContribution(
            student_id="Greg", contribution_score=4,
            primary_contributions=["Started and iterated on the DB schema design (DB-1, still In Progress)"],
            evidence=["Commits 'Start DB schema' (+20/-0) and 'Fix DB schema' (+5/-2)", "Jira DB-1 remains In Progress", "Received peer ratings of 2 and 3 out of 5"],
        ),
        MemberContribution(
            student_id="Frank", contribution_score=4,
            primary_contributions=["Attempted and later refactored the API implementation (DB-2, still To Do)"],
            evidence=["Commits 'Attempt to implement API' (+30/-5) and 'Refactor API' (+5/-1)", "Jira DB-2 remains To Do", "Described by teammates as 'slow to respond' and 'not helpful'"],
        ),
        MemberContribution(
            student_id="Hank", contribution_score=4,
            primary_contributions=["Wrote and updated a small set of tests (DB-3, still To Do)"],
            evidence=["Commits 'Write some tests' (+10/-0) and 'Update tests' (+2/-0)", "Jira DB-3 remains To Do", "Described by teammates as 'not proactive' and doing 'the bare minimum'"],
        ),
    ],
    executive_summary="Team_Gamma made incremental progress across all three planned tickets but completed none of them by sprint end. Peer evaluations were uniformly mediocre (2-3 out of 5), with each member criticizing another's pace or proactivity — suggesting broad underperformance rather than one specific blocker.",
    key_recommendations=[
        "Identify what's blocking DB-1 from moving out of In Progress.",
        "Hold a team check-in to surface the blockers implied by the mutual low peer ratings.",
        "Prioritize closing DB-3 given related test commits already exist.",
    ],
)

good_collab_low_output_grade = SprintAssessment(
    team_id=good_collab_low_output_team.team_id,
    sprint_id=good_collab_low_output_team.sprint_id,
    prompt_version="v1.0",
    overall_score=5.17,  # mean of all 6 dimensions: (6+5+5+5+9+1)/6
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=6,
            justification="Commits are small and clean, but there are only 4 of them across the whole sprint.",
            evidence_citations=[
                _cite("Ivy's 'Add login page skeleton' commit is a focused +35/-2 change."),
                _cite("Kim's 'Add basic form validation' commit is a targeted +40/-5 change."),
            ],
            strengths=["Every commit is small and single-purpose"],
            areas_for_improvement=["Only 4 commits total for a 3-person team across the sprint"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=5,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                _cite("None of the 4 commits touch a tests/ file — changes are to auth/login_page.py, components/navbar.css, and forms/validation.py only."),
            ],
            strengths=["No untested large features were rushed out"],
            areas_for_improvement=["No dedicated testing ticket or commit exists this sprint"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=5,
            justification="No dedicated documentation ticket or commit exists, though ticket summaries are clear.",
            evidence_citations=[
                _cite("Jira ticket summaries (DEL-1 through DEL-4) are short but clear."),
            ],
            strengths=["Ticket summaries are unambiguous"],
            areas_for_improvement=["No README or user-facing documentation was produced"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=5,
            justification="Only 2 of 4 planned tickets are Done; the other 2 are still In Progress or To Do.",
            evidence_citations=[
                _cite("Jira tickets DEL-1 and DEL-2 are marked Done."),
                _cite("Jira ticket DEL-3 is still In Progress and DEL-4 is still To Do."),
            ],
            strengths=["The 2 completed tickets were fully finished, not left half-done"],
            areas_for_improvement=["Half of the sprint's planned tickets did not reach Done"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=9,
            justification="All 6 peer evaluations rate teammates 4 or 5 out of 5, with specific, warm comments.",
            evidence_citations=[
                _cite("Jack rated Ivy 5/5: 'Ivy keeps the team organized and unblocks people fast.'"),
                _cite("Kim rated Ivy 5/5: 'Ivy is a great communicator and very supportive.'"),
            ],
            strengths=["Every peer evaluation is positive and specific, with no signs of friction"],
            areas_for_improvement=["No constructive critique appears anywhere in peer feedback"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd",
            score=1,
            justification="No CI/CD artifact exists in this sprint: no workflow or pipeline configuration, no Dockerfile, and artifact_metrics is empty. Band 1-2 applies.",
            evidence_citations=[
                _cite("Commit d1e2f3a and the other 3 commits touch only auth/login_page.py, components/navbar.css and forms/validation.py; no pipeline configuration is present."),
                _cite("Ticket DEL-1 'Build login page' is feature work, not a CI build; no DEL ticket covers CI, build or deployment work."),
            ],
            strengths=[],
            areas_for_improvement=["Add a CI workflow that runs the test suite on every push", "No automated build or deployment step exists to attribute to any member"],
        ),
    ),
    member_contributions=[
        MemberContribution(
            student_id="Ivy", contribution_score=6,
            primary_contributions=["Built the login page (DEL-1)", "Started the responsive layout pass (DEL-4)"],
            evidence=["Commits 'Add login page skeleton' and 'Fix navbar responsiveness'", "Jira DEL-1 marked Done, DEL-4 still To Do"],
        ),
        MemberContribution(
            student_id="Jack", contribution_score=6,
            primary_contributions=["Styled the navbar (DEL-2)"],
            evidence=["Commit 'Style navbar component' (+25/-1)", "Jira DEL-2 marked Done"],
        ),
        MemberContribution(
            student_id="Kim", contribution_score=5,
            primary_contributions=["Started form validation (DEL-3, still In Progress)"],
            evidence=["Commit 'Add basic form validation' (+40/-5)", "Jira DEL-3 still In Progress"],
        ),
    ],
    executive_summary="Team_Delta showed strong, warm collaboration with universally positive peer feedback, but delivered only 2 of 4 planned tickets this sprint — the shortfall is in output, not teamwork.",
    key_recommendations=[
        "Scope fewer tickets per sprint, or start them earlier — DEL-3 and DEL-4 both stalled.",
        "Add a dedicated testing ticket next sprint.",
    ],
)

imbalanced_high_output_grade = SprintAssessment(
    team_id=imbalanced_high_output_team.team_id,
    sprint_id=imbalanced_high_output_team.sprint_id,
    prompt_version="v1.0",
    overall_score=5.33,  # mean of all 6 dimensions: (9+6+6+8+2+1)/6
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=9,
            justification="Liam's 4 commits are large but well-scoped, each covering one part of the payments feature.",
            evidence_citations=[
                _cite("Liam's 'Build payment processing service' commit is a substantial +280/-15 change."),
                _cite("Liam's 'Implement refund flow' commit is a focused +160/-10 change."),
            ],
            strengths=["Each commit maps cleanly to one payments sub-feature"],
            areas_for_improvement=["Commits this large would benefit from incremental PR review"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=6,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                _cite("No Jira ticket or commit in this sprint references writing or updating tests."),
            ],
            strengths=["The refund flow, a financially sensitive feature, still shipped without visible defects reported"],
            areas_for_improvement=["No dedicated testing ticket or commit exists for the payments module"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=6,
            justification="No dedicated documentation ticket exists, though Liam's commit messages clearly describe scope.",
            evidence_citations=[
                _cite("Jira tickets PAY-1 through PAY-4 have clear, specific summaries."),
                _cite("None of the 6 commits touch a docs/ or README file, despite introducing 4 new payments modules (service.py, webhooks.py, refunds.py, audit_log.py)."),
            ],
            strengths=["Ticket and commit descriptions are specific and traceable"],
            areas_for_improvement=["No README or API documentation was produced for the new payments service"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=8,
            justification="All 4 planned Jira tickets are marked Done, totaling 21 story points.",
            evidence_citations=[
                _cite("Jira tickets PAY-1 through PAY-4 are all marked Done."),
                _cite("21 of 21 planned story points were delivered."),
            ],
            strengths=["100% ticket completion for the sprint"],
            areas_for_improvement=["All delivery risk was concentrated in a single contributor"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=2,
            justification="One member did all planned work while the other two made only token commits; peer evaluations confirm this directly.",
            evidence_citations=[
                _cite("Maya rated Liam 5/5: 'Liam carried the entire payments module practically by himself.'"),
                _cite("Liam rated Maya and Noah 2/5 each, citing a one-line config fix and a .gitignore update as their only contributions."),
            ],
            strengths=["Liam acknowledged the imbalance directly rather than overstating teammates' contributions"],
            areas_for_improvement=["Maya and Noah did not pick up any of the 4 planned tickets", "Workload concentration this severe is a project-risk concern even though delivery succeeded"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd",
            score=1,
            justification="No CI/CD artifact exists in this sprint. The only infrastructure-adjacent file is a .gitignore edit, which is not pipeline configuration, and artifact_metrics is empty. Band 1-2 applies.",
            evidence_citations=[
                _cite("Commit e1a2b3c and the other 5 commits touch payments/service.py, payments/refunds.py and .gitignore; a .gitignore edit is not pipeline configuration, and no workflow or Dockerfile is present."),
                _cite("Ticket PAY-1 'Build payment processing service' is feature work, not a CI build; no PAY ticket covers CI, build or deployment work."),
            ],
            strengths=[],
            areas_for_improvement=["Add a CI workflow so the payments module is tested automatically rather than relying on one member", "No automated build or deployment step exists to attribute to any member"],
        ),
    ),
    member_contributions=[
        MemberContribution(
            student_id="Liam", contribution_score=10,
            primary_contributions=["Built the entire payments module (PAY-1 through PAY-4)"],
            evidence=["4 commits totaling 780+ lines", "All 4 Jira tickets assigned to and completed by Liam"],
        ),
        MemberContribution(
            student_id="Maya", contribution_score=2,
            primary_contributions=["Fixed a typo in a config comment"],
            evidence=["Commit 'Fix typo in payment config comment' (+1/-1)", "0 Jira tickets assigned"],
        ),
        MemberContribution(
            student_id="Noah", contribution_score=2,
            primary_contributions=["Updated .gitignore"],
            evidence=["Commit 'Update .gitignore' (+2/-0)", "0 Jira tickets assigned"],
        ),
    ],
    executive_summary="Team_Epsilon delivered all 4 planned payments tickets on time and with clean code, but the work was almost entirely done by one member — a severe workload imbalance that peer evaluations confirm directly, even though overall delivery was excellent.",
    key_recommendations=[
        "Redistribute payments-module tickets across all 3 members next sprint.",
        "Add a dedicated testing ticket given payments is a financially sensitive feature.",
    ],
)

lone_contributor_poor_outcome_grade = SprintAssessment(
    team_id=lone_contributor_poor_outcome_team.team_id,
    sprint_id=lone_contributor_poor_outcome_team.sprint_id,
    prompt_version="v1.0",
    overall_score=2.67,  # mean of all 6 dimensions: (4+3+3+3+2+1)/6
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=4,
            justification="All 3 commits are small and one is explicitly unfinished, reflecting a rushed, overloaded effort.",
            evidence_citations=[
                _cite("Uma's second commit message is literally 'WIP, ran out of time'."),
                _cite("Uma's third commit, 'Partial fix for report export bug', is only a +15/-3 partial change."),
            ],
            strengths=["Uma's first commit did establish a working report generation core"],
            areas_for_improvement=["Two of three commits are explicitly incomplete work"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=3,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                _cite("No Jira ticket or commit in this sprint references writing or updating tests."),
            ],
            strengths=[],
            areas_for_improvement=["No testing was possible given the feature itself was left incomplete"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=3,
            justification="No documentation was produced, consistent with the feature not reaching a stable state.",
            evidence_citations=[
                _cite("No commit or Jira ticket this sprint references documentation."),
            ],
            strengths=[],
            areas_for_improvement=["No documentation exists for the partially-built reporting feature"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=3,
            justification="Only 1 of 4 planned tickets is Done; the rest are In Progress or To Do, all still assigned to a single member.",
            evidence_citations=[
                _cite("Jira ticket REP-1 is marked Done."),
                _cite("Jira tickets REP-2, REP-3, and REP-4 remain In Progress or To Do, all assigned to Uma."),
            ],
            strengths=["The one completed ticket (REP-1) was fully finished"],
            areas_for_improvement=["3 of 4 tickets did not reach Done, and all 4 were carried by one person"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=2,
            justification="One member did all the work and it still wasn't enough — peer evaluations confirm both the imbalance and the shortfall.",
            evidence_citations=[
                _cite("Uma rated Victor 1/5: 'Victor did not contribute to any report tickets.'"),
                _cite("Wei rated Uma 3/5: 'Uma carried the whole feature alone and it was too much for one person.'"),
            ],
            strengths=["Uma's effort was real and acknowledged by teammates, not just self-reported"],
            areas_for_improvement=["Two of three members made zero commits", "The team should not have let all 4 tickets sit with one person"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd",
            score=1,
            justification="No CI/CD artifact exists in this sprint: no workflow or pipeline configuration, no Dockerfile, and artifact_metrics is empty. Band 1-2 applies.",
            evidence_citations=[
                _cite("All 3 commits b1a2b3c, b2b3c4d and b3c4d5e touch only reports/generator.py and reports/export.py; no pipeline or workflow file is present."),
                _cite("Ticket REP-1 'Build report generation core' is feature work, not a CI build; no REP ticket covers CI, build or deployment work."),
            ],
            strengths=[],
            areas_for_improvement=["Add a CI workflow that runs the test suite on every push", "No automated build or deployment step exists to attribute to any member"],
        ),
    ),
    member_contributions=[
        MemberContribution(
            student_id="Uma", contribution_score=6,
            primary_contributions=["Started report generation (REP-1, Done)", "Attempted report export and scheduling (REP-2, REP-3, incomplete)"],
            evidence=["3 commits, one explicitly marked 'WIP, ran out of time'", "All 4 Jira tickets assigned to Uma, only 1 Done"],
        ),
        MemberContribution(
            student_id="Victor", contribution_score=1,
            primary_contributions=[],
            evidence=["0 commits this sprint", "Rated 1/5 by Uma: 'did not contribute to any report tickets'"],
        ),
        MemberContribution(
            student_id="Wei", contribution_score=1,
            primary_contributions=[],
            evidence=["0 commits this sprint", "Rated 2/5 by Uma: 'helped plan but wrote no code'"],
        ),
    ],
    executive_summary="Team_Theta's reporting feature was carried entirely by one member, Uma, and it still wasn't enough — only 1 of 4 planned tickets reached Done, with the other two teammates making zero commits. Peer evaluations confirm both the imbalance and that the team's overall outcome was poor despite Uma's individual effort.",
    key_recommendations=[
        "Redistribute the remaining REP tickets across all 3 members immediately.",
        "Investigate why Victor and Wei made zero commits this sprint.",
    ],
)



GOLD_ASSESSMENTS: tuple[SprintAssessment, ...] = (
    high_performing_grade,
    struggling_grade,
    good_collab_low_output_grade,
    imbalanced_high_output_grade,
    lone_contributor_poor_outcome_grade,
)


def _assert_gold_is_consistent() -> None:
    """Fail at import if a gold assessment has drifted from the live rubric.

    Two invariants, both of which were silently violated before:

    1. Every gold scores every dimension in DIMENSIONS. The `cicd` dimension
       was added to the rubric in "feature/add cicd rubric" and these five
       golds were never backfilled, so `cicd` sat unscored. Nothing broke
       loudly -- the judge pipeline just computed `grade_abs_error_cicd` as
       None on every row and quietly measured 5 dimensions out of 6.
    2. `overall_score` equals the mean of the scored dimensions, which is how
       services/evaluator.py derives it (`average_score = sum(...) / len(...)`).
       While gold averaged 5 dimensions and a real candidate averaged 6,
       `grade_abs_error_overall` carried a systematic bias in the candidate's
       disfavour that no metric would have revealed.

    Raising here is deliberate: a stale benchmark produces confident,
    plausible numbers, which is far worse than an import error.
    """
    for gold in GOLD_ASSESSMENTS:
        missing = [
            dimension
            for dimension in DIMENSIONS
            if getattr(gold.rubric_scores, dimension, None) is None
        ]
        if missing:
            raise ValueError(
                f"Gold assessment for team {gold.team_id} is missing rubric "
                f"dimension(s) {missing}. Every dimension in DIMENSIONS needs a "
                "human reference score, or judge metrics that compare against "
                "gold silently skip it."
            )
        scored = gold.rubric_scores.scored()
        expected = round(sum(score.score for score in scored) / len(scored), 2)
        if abs(gold.overall_score - expected) > 0.01:
            raise ValueError(
                f"Gold assessment for team {gold.team_id} has "
                f"overall_score={gold.overall_score} but its {len(scored)} "
                f"dimension scores average {expected}. services/evaluator.py "
                "derives overall_score as that mean, so gold must too or "
                "grade_abs_error_overall is biased."
            )


_assert_gold_is_consistent()


if __name__ == "__main__":
    for label, grade in [
        ("Team_Alpha (High-Performing)", high_performing_grade),
        ("Team_Gamma (Struggling)", struggling_grade),
        ("Team_Delta (Good collab, low output)", good_collab_low_output_grade),
        ("Team_Epsilon (Imbalanced, high output)", imbalanced_high_output_grade),
        ("Team_Theta (Lone contributor, poor outcome)", lone_contributor_poor_outcome_grade),
    ]:
        print(f"SUCCESS! {label} schema works.")
        print(grade.model_dump_json(indent=2))