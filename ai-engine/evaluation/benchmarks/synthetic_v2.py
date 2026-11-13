"""Synthetic benchmark set v2: five teams (sprint 2026-08-10_to_2026-08-21) and their gold."""

import hashlib
from datetime import datetime, timedelta, timezone

from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo, FileDiff
from schemas.jira import JiraTicket
from schemas.member_contribution import MemberContribution
from schemas.peer_evaluation import PeerEvaluation
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment

from evaluation.benchmarks import DATA_DIR

'''
Gold scores live in evaluation/benchmarks/data/gold/<team>_GOLD.json (loaded at the bottom).
    code quality, testing, documentation, requirements, collaboration, cicd -> overall
Alpha   9 9 8 9 9 8 -> 8.67   (all dimensions 8-10)
Gamma   3 2 1 2 3 1 -> 2.00   (low output, quality issues)
Delta   6 6 6 6 8 5 -> 6.17   (high teamwork, little work)
Epsilon 8 7 7 8 2 8 -> 6.67   (lots of work, one member carries)
Theta   5 3 3 4 1 4 -> 3.33   (solo effort, poor results)
'''

SGT = timezone(timedelta(hours=8))
SPRINT_ID = "2026-08-10_to_2026-08-21"

def _sha(team, n):
    return hashlib.sha1(f"{team}:{n}".encode(), usedforsecurity=False).hexdigest()
def _ts(day, hh, mm, ss=0): return datetime(2026, 8, day, hh, mm, ss, tzinfo=SGT)
def _file(name, change="modified", added=0, deleted=0): return FileDiff(filename=name, change_type=change, lines_added=added, lines_deleted=deleted)
def _commit(team, n, author, message, ts, files):
    return CommitInfo(sha=_sha(team, n), author=author, message=message, timestamp=ts,
        lines_added=sum(f.lines_added for f in files), lines_deleted=sum(f.lines_deleted for f in files), files_changed=files)
def _ticket(tid, summary, assignee, status, issue_type, points, ts):
    return JiraTicket(ticket_id=tid, summary=summary, assignee=assignee, status=status, issue_type=issue_type, story_points=points, sprint_id=SPRINT_ID, timestamp=ts)
# Citations must be dicts: ModelOutput.coerce_citations mangles EvidenceCitation objects
def _cite(identifier, reason): return {"identifier": identifier, "reason": reason}
def _dim(dimension, score, justification, citations, strengths, improvements):
    return RubricDimensionScore(dimension=dimension, score=score, justification=justification, evidence_citations=citations, strengths=strengths, areas_for_improvement=improvements)

# The Best Team (strong on every dimension, even workload)
A = "Team_Alpha"
high_performing_team = ArtifactBundle(team_id=A, sprint_id=SPRINT_ID, commits=[
    _commit(A, 1, "Charlie", "AUTH-4: Add GitHub Actions CI running pytest and flake8 on PRs", _ts(10, 10, 42, 17), [
        _file(".github/workflows/ci.yml", "added", 38), _file("requirements-dev.txt", "added", 6), _file(".flake8", "added", 5)]),
    _commit(A, 2, "Alice", "AUTH-1: Add JWT issue/verify middleware with configurable expiry", _ts(11, 14, 5, 33), [
        _file("auth/middleware.py", "added", 142), _file("auth/config.py", "modified", 12, 3), _file(".DS_Store", "added")]),
    _commit(A, 3, "Bob", "AUTH-2: Add unit tests for token issue, expiry and tampered signatures", _ts(12, 16, 20, 48), [
        _file("tests/test_middleware.py", "added", 118), _file("tests/conftest.py", "added", 24)]),
    _commit(A, 4, "Bob", "Merge pull request #4 from alpha-team/feature/AUTH-1-jwt-middleware", _ts(13, 11, 2, 9), []),
    _commit(A, 5, "Charlie", "AUTH-3: Implement refresh-token rotation and revocation list", _ts(14, 15, 37, 51), [
        _file("auth/refresh.py", "added", 96), _file("auth/service.py", "modified", 41, 18), _file("tests/test_refresh.py", "added", 77)]),
    _commit(A, 6, "Bob", "AUTH-2: Add integration tests for login -> refresh -> logout flow", _ts(17, 10, 14, 26), [
        _file("tests/integration/test_auth_flow.py", "added", 103),
        _file("tests/__pycache__/conftest.cpython-311-pytest-8.2.0.pyc", "added")]),
    _commit(A, 7, "Charlie", "AUTH-4: Build and push Docker image in CI after tests pass", _ts(18, 17, 48, 2), [
        _file(".github/workflows/ci.yml", "modified", 27, 4), _file("Dockerfile", "added", 19), _file(".dockerignore", "added", 7)]),
    _commit(A, 8, "Alice", "Document auth endpoints, env vars and local setup in README", _ts(19, 13, 26, 40), [
        _file("README.md", "modified", 64, 6), _file("docs/auth-api.md", "added", 88)]),
], jira_tickets=[
    _ticket("AUTH-1", "JWT issue/verify middleware with configurable expiry", "Alice", "Done", "Story", 8, _ts(13, 11, 5)),
    _ticket("AUTH-2", "Unit and integration tests for auth middleware and refresh flow", "Bob", "Done", "Task", 5, _ts(17, 10, 30)),
    _ticket("AUTH-3", "Refresh-token rotation and revocation", "Charlie", "Done", "Story", 5, _ts(14, 16, 2)),
    _ticket("AUTH-4", "CI pipeline: lint, test and Docker build on every PR", "Charlie", "Done", "Task", 3, _ts(18, 18, 5)),
], peer_evaluations=[
    PeerEvaluation(evaluator="Bob", evaluatee="Alice", rating=5, comments="Alice's middleware PR was clean and she walked us through the token design before merging."),
    PeerEvaluation(evaluator="Charlie", evaluatee="Alice", rating=5, comments="Reviewed my refresh-rotation PR within a few hours with really useful comments."),
    PeerEvaluation(evaluator="Alice", evaluatee="Bob", rating=5, comments="Bob's tampered-signature tests caught a real expiry bug before we merged."),
    PeerEvaluation(evaluator="Charlie", evaluatee="Bob", rating=4, comments="Solid tests and good README, could have started the integration tests earlier."),
    PeerEvaluation(evaluator="Alice", evaluatee="Charlie", rating=5, comments="Charlie set up CI on day one so every PR was tested automatically."),
    PeerEvaluation(evaluator="Bob", evaluatee="Charlie", rating=4, comments="Strong on refresh tokens and Docker, but his PR descriptions were sometimes too brief."),
])

high_performing_grade = SprintAssessment(
    team_id=high_performing_team.team_id, sprint_id=high_performing_team.sprint_id, prompt_version="v1.0",
    overall_score=8.67,  # (9+9+8+9+9+8)/6
    rubric_scores=RubricsScore(
        code_quality=_dim("code_quality", 9,
            "8 commits (+867/-31) split across all three members (Alice 2, Bob 3, Charlie 3). Every feature commit is single-purpose and prefixed with its Jira key (e.g. 'AUTH-3: Implement refresh-token rotation and revocation list'), and AUTH-1 reached main through a reviewed PR (#4). Only nit: a .DS_Store file was committed with the AUTH-1 middleware.",
            [_cite(_sha(A, 5), "'AUTH-3: Implement refresh-token rotation and revocation list' (+214/-18) ships the feature and its own test file in one focused commit."),
             _cite(_sha(A, 2), "'AUTH-1: Add JWT issue/verify middleware with configurable expiry' (+154/-3) is a substantial, clearly described core contribution."),
             _cite(_sha(A, 4), "Bob merging Alice's feature/AUTH-1 branch via PR #4 shows peer review before the code reached main.")],
            ["Descriptive, ticket-keyed commit messages throughout", "Small single-purpose commits from every member", "Feature branch merged through a pull request"],
            ["Add .DS_Store to .gitignore (committed in the AUTH-1 commit)", "Only one PR merge is visible; route every feature branch through a PR"]),
        testing=_dim("testing", 9,
            "AUTH-2, a dedicated testing ticket, is Done, and three explicit test commits add 322 test lines: unit tests for token issue/expiry/tampering, refresh-rotation tests, and an integration test of the login -> refresh -> logout flow. The AUTH-4 CI workflow runs pytest on every PR. No coverage figure is reported.",
            [_cite("AUTH-2", "Dedicated testing ticket 'Unit and integration tests for auth middleware and refresh flow' is Done, assigned to Bob."),
             _cite(_sha(A, 3), "'AUTH-2: Add unit tests for token issue, expiry and tampered signatures' adds tests/test_middleware.py and tests/conftest.py (+142)."),
             _cite(_sha(A, 6), "'AUTH-2: Add integration tests for login -> refresh -> logout flow' adds tests/integration/test_auth_flow.py (+103).")],
            ["Testing tracked as its own ticket and completed", "Both unit and integration tests", "Tests shipped alongside AUTH-3 in the same commit"],
            ["No coverage percentage is reported", "Integration tests arrived on day 8, after most features were merged"]),
        documentation=_dim("documentation", 8,
            "'Document auth endpoints, env vars and local setup in README' (+152/-6) explicitly updates README.md and adds docs/auth-api.md, and every Jira summary states its deliverable precisely. Held below 9 because all documentation landed in one end-of-sprint commit with no ticket key, so docs lagged the features and the work is untracked in Jira.",
            [_cite(_sha(A, 8), "'Document auth endpoints, env vars and local setup in README' updates README.md and adds docs/auth-api.md (+152/-6)."),
             _cite("AUTH-1", "'JWT issue/verify middleware with configurable expiry' clearly documents what the completed ticket delivered."),
             _cite("AUTH-4", "'CI pipeline: lint, test and Docker build on every PR' is precise, but no ticket covers the README/API docs work.")],
            ["Dedicated README and API documentation file", "Specific, informative Jira summaries"],
            ["Track documentation as a ticket and update docs with each feature", "Documentation arrived only on day 10 in a single commit"]),
        requirements=_dim("requirements", 9,
            "All 4 Jira tickets (AUTH-1 to AUTH-4) are Done, delivering 21 of 21 story points across two Stories and two Tasks, with nothing left In Progress, In Review or Blocked. Held at 9 rather than 10 only because the committed scope is modest (4 tickets, 21 points) for a three-person, two-week sprint.",
            [_cite("AUTH-1", "Story 'JWT issue/verify middleware with configurable expiry' (8 points) is Done."),
             _cite("AUTH-3", "Story 'Refresh-token rotation and revocation' (5 points) is Done."),
             _cite("AUTH-4", "Task 'CI pipeline: lint, test and Docker build on every PR' (3 points) is Done.")],
            ["100% of tickets and story points completed", "Every ticket estimated and assigned"],
            ["Scope is modest; consider committing to more points next sprint", "Add a ticket for documentation work"]),
        collaboration=_dim("collaboration", 9,
            "Peer ratings average 4.67 (28/30: four 5s, two 4s) and every comment cites specific work (PR reviews, tests that caught a bug, CI on day one). Workload is near-even by story points: Alice 8 (AUTH-1), Charlie 8 (AUTH-3, AUTH-4), Bob 5 (AUTH-2). The two 4/5 ratings carry constructive critique, which is a healthy signal.",
            [_cite("Charlie -> Alice (5/5)", "'Reviewed my refresh-rotation PR within a few hours' shows active cross-member code review."),
             _cite("Charlie -> Bob (4/5)", "'Could have started the integration tests earlier' is honest, specific constructive feedback."),
             _cite("AUTH-2", "Bob's 5-point testing ticket sits beside Alice's 8 and Charlie's 8 points, so no member is idle.")],
            ["High, specific peer ratings for every member", "Story points spread across all three members"],
            ["Bob carries fewer points (5 vs 8); balance estimates next sprint", "Act on the PR-description feedback"]),
        cicd=_dim("cicd", 8,
            "'AUTH-4: Add GitHub Actions CI running pytest and flake8 on PRs' lands on day one, and 'AUTH-4: Build and push Docker image in CI after tests pass' extends .github/workflows/ci.yml and adds a Dockerfile, so every PR is linted, tested and containerised. Minor gap: no deployment stage, so this is CI without CD.",
            [_cite(_sha(A, 1), "'AUTH-4: Add GitHub Actions CI running pytest and flake8 on PRs' adds .github/workflows/ci.yml on the first day of the sprint."),
             _cite(_sha(A, 7), "'AUTH-4: Build and push Docker image in CI after tests pass' adds a Dockerfile and gates the image build on tests."),
             _cite(".github/workflows/ci.yml", "Added on 08-10 and extended on 08-18, showing the pipeline evolved with the code.")],
            ["CI in place from day one", "Docker image build gated on passing tests"],
            ["Add a deploy stage (staging) to complete CD", "Publish test/coverage results as pipeline artifacts"]),
    ),
    member_contributions=[
        MemberContribution(student_id="Alice", contribution_score=9,
            primary_contributions=["JWT issue/verify middleware (AUTH-1, 8 points)", "README and docs/auth-api.md"],
            evidence=["2 commits, +306/-9", f"{_sha(A, 2)} AUTH-1: Add JWT issue/verify middleware with configurable expiry", "Peer ratings 5 and 5"]),
        MemberContribution(student_id="Bob", contribution_score=8,
            primary_contributions=["Unit and integration test suite (AUTH-2, 5 points)", "Reviewed and merged the AUTH-1 PR (#4)"],
            evidence=["3 commits (1 PR merge), +245/-0", f"{_sha(A, 3)} AUTH-2: Add unit tests for token issue, expiry and tampered signatures", "Peer ratings 5 and 4"]),
        MemberContribution(student_id="Charlie", contribution_score=9,
            primary_contributions=["Refresh-token rotation (AUTH-3)", "GitHub Actions CI and Docker build (AUTH-4)"],
            evidence=["3 commits, +316/-22", f"{_sha(A, 5)} AUTH-3: Implement refresh-token rotation and revocation list", "Peer ratings 5 and 4"]),
    ],
    executive_summary="In the 2026-08-10 to 2026-08-21 sprint Team_Alpha delivered all 4 tickets (21/21 points) for a JWT auth service: middleware, refresh-token rotation, a unit and integration test suite, and a GitHub Actions pipeline that lints, tests and builds a Docker image on every PR. Commits are descriptive and ticket-keyed, work is evenly shared, and peers rate each other 4.67/5 on average. Gaps are minor: no deploy stage, late untracked documentation and no coverage report.",
    strengths=["100% ticket completion with ticket-keyed commits", "Tests and CI built alongside the features", "Even workload and specific, high peer ratings"],
    weaknesses=["No deployment stage in the pipeline", "Documentation delivered late in one untracked commit", "No coverage figure"],
    key_recommendations=["Add a staging deploy job to ci.yml so the pipeline covers CD.", "Report test coverage in CI and set a minimum threshold.", "Create a documentation ticket and update docs with each feature PR.", "Route every feature branch through a reviewed PR, not just AUTH-1."],
)

# The Struggling Team (little work, nothing finished)
G = "Team_Gamma"
struggling_team = ArtifactBundle(team_id=G, sprint_id=SPRINT_ID, commits=[
    _commit(G, 1, "Greg", "Start DB schema", _ts(10, 21, 14, 38), [_file("db/schema.py", "added", 20), _file(".DS_Store", "added")]),
    _commit(G, 2, "Frank", "Attempt to implement API", _ts(12, 23, 47, 9), [_file("api/routes.py", "added", 30)]),
    _commit(G, 3, "Hank", "add models", _ts(15, 1, 12, 52), [_file("db/models.py", "added", 14), _file("db/__pycache__/schema.cpython-311.pyc", "added")]),
    _commit(G, 4, "Greg", "Fix DB schema", _ts(17, 22, 30, 4), [_file("db/schema.py", "modified", 5, 2)]),
    _commit(G, 5, "Greg", "Merge branch 'main' of https://github.com/gamma-team/db-project", _ts(17, 22, 36, 21), []),
    _commit(G, 6, "Frank", "Refactor API", _ts(19, 23, 55, 40), [_file("api/routes.py", "modified", 5, 1)]),
    _commit(G, 7, "Frank", "fix", _ts(19, 23, 58, 17), [_file("api/routes.py", "modified", 2, 2)]),
    _commit(G, 8, "Hank", "update", _ts(20, 23, 21, 3), [_file("db/models.py", "modified", 3, 1), _file(".DS_Store", "modified")]),
], jira_tickets=[
    _ticket("DB-1", "Design DB", "Greg", "In Progress", "Story", 5, _ts(17, 22, 41)),
    _ticket("DB-2", "Setup ORM", "Frank", "To Do", "Task", 3, _ts(10, 9, 0)),
    _ticket("DB-3", "Write DB Tests", "Hank", "To Do", "Task", 2, _ts(10, 9, 0)),
], peer_evaluations=[
    PeerEvaluation(evaluator="Greg", evaluatee="Frank", rating=3, comments="Frank was slow to respond."),
    PeerEvaluation(evaluator="Frank", evaluatee="Greg", rating=3, comments="Greg tried his best but struggled to get task done"),
    PeerEvaluation(evaluator="Hank", evaluatee="Greg", rating=2, comments="Greg didn't contribute much."),
    PeerEvaluation(evaluator="Hank", evaluatee="Frank", rating=2, comments="Frank was not helpful."),
    PeerEvaluation(evaluator="Greg", evaluatee="Hank", rating=3, comments="Hank was not proactive."),
    PeerEvaluation(evaluator="Frank", evaluatee="Hank", rating=3, comments="Hank did the bare minimum."),
])

struggling_grade = SprintAssessment(
    team_id=struggling_team.team_id, sprint_id=struggling_team.sprint_id, prompt_version="v1.0",
    overall_score=2.0,  # (3+2+1+2+3+1)/6
    rubric_scores=RubricsScore(
        code_quality=_dim("code_quality", 3,
            "8 commits add only +79/-6 lines; the largest is 'Attempt to implement API' (+30). Messages are vague ('fix', 'update', 'Refactor API' for a +5/-1 change), 7 of 8 commits land between 22:00 and 01:15, and .DS_Store is committed twice. Some real schema, model and route code exists, which keeps this just above 1-2.",
            [_cite(_sha(G, 2), "'Attempt to implement API' (+30) is the largest commit of the sprint and its message signals unfinished work."),
             _cite(_sha(G, 7), "'fix' (+2/-2 on api/routes.py) three minutes after 'Refactor API' is an uninformative trial-and-error commit."),
             _cite(_sha(G, 8), "'update' (+3/-1 on db/models.py) also re-commits .DS_Store, a macOS junk file.")],
            ["Each member committed some code", "Schema, models and routes are separated into modules"],
            ["Write messages that say what changed and why", "Commit earlier in the sprint instead of near midnight", "Add .DS_Store and __pycache__/ to .gitignore"]),
        testing=_dim("testing", 2,
            "No test file appears in any of the 8 commits; only db/, api/ and junk files change. The only testing evidence is DB-3 'Write DB Tests', which is still To Do. Scored 2 rather than 1 because testing was at least planned as a ticket.",
            [_cite("DB-3", "'Write DB Tests' (2 points, Hank) is still To Do at sprint end, so the planned testing never started."),
             _cite(_sha(G, 3), "'add models' adds db/models.py with no accompanying test file."),
             _cite(_sha(G, 6), "'Refactor API' changes api/routes.py with no test to show behaviour was preserved.")],
            ["A testing ticket exists in the backlog"],
            ["Start DB-3 and add tests for db/schema.py and api/routes.py", "Add at least one test with every feature commit"]),
        documentation=_dim("documentation", 1,
            "No README, docs/ or comment-only change exists in any of the 8 commits, and Jira summaries are two-word labels ('Design DB', 'Setup ORM') with no description of the intended work. No documentation effort is recorded in any system.",
            [_cite("DB-1", "'Design DB' is a two-word summary with no detail on what the schema should contain."),
             _cite("DB-2", "'Setup ORM' gives no description or acceptance criteria for the task."),
             _cite(_sha(G, 1), "'Start DB schema' adds db/schema.py with no README or docs explaining the design.")],
            [],
            ["Add a README with setup steps and the schema design", "Write ticket summaries that describe the deliverable"]),
        requirements=_dim("requirements", 2,
            "0 of 3 tickets are Done: DB-1 'Design DB' (5 points) is In Progress, while DB-2 'Setup ORM' (3) and DB-3 'Write DB Tests' (2) are still To Do. 0 of 10 story points delivered. Scored 2 rather than 1 only because DB-1 shows some progress.",
            [_cite("DB-1", "'Design DB' (5 points) is still In Progress at sprint end."),
             _cite("DB-2", "'Setup ORM' (3 points) never left To Do."),
             _cite("DB-3", "'Write DB Tests' (2 points) never left To Do.")],
            ["All tickets estimated and assigned"],
            ["Break DB-1 into smaller tickets that can be finished within the sprint", "Move tickets as work starts so the board reflects reality"]),
        collaboration=_dim("collaboration", 3,
            "Peer ratings average 2.67 (16/30, only 2s and 3s) and comments describe slow responses and minimal effort ('Hank did the bare minimum'). Tickets are spread one per member (5/3/2 points), but none is Done, so the even split reflects shared under-delivery rather than teamwork. Band 3-5 by rating, scored at its floor.",
            [_cite("Hank -> Greg (2/5)", "'Greg didn't contribute much' is one of two 2/5 ratings in the team."),
             _cite("Frank -> Hank (3/5)", "'Hank did the bare minimum' shows low trust in a teammate's effort."),
             _cite("DB-2", "Frank's 3-point ticket is still To Do, consistent with 'Frank was slow to respond'.")],
            ["Every member was assigned a ticket"],
            ["Hold short stand-ups to surface blockers", "Pair on DB-1 so the schema is finished together"]),
        cicd=_dim("cicd", 1,
            "None of the 8 commits touches a workflow, Dockerfile, docker-compose or any build or deploy file; changes are limited to db/schema.py, db/models.py, api/routes.py and junk files. No CI/CD practice is evident.",
            [_cite(_sha(G, 1), "'Start DB schema' sets up the repo with no pipeline or build configuration."),
             _cite(_sha(G, 5), "'Merge branch main' integrates work with no automated check of any kind."),
             _cite(_sha(G, 4), "'Fix DB schema' fixes code manually; no CI exists to catch the original error.")],
            [],
            ["Add a minimal GitHub Actions workflow that installs dependencies and runs tests", "Containerise the app once it runs"]),
    ),
    member_contributions=[
        MemberContribution(student_id="Greg", contribution_score=3, primary_contributions=["Started the DB schema (DB-1, In Progress)"],
            evidence=["3 commits (1 merge), +25/-2", f"{_sha(G, 1)} Start DB schema", "Peer ratings 3 and 2"]),
        MemberContribution(student_id="Frank", contribution_score=3, primary_contributions=["Draft API routes (not his assigned DB-2 ticket)"],
            evidence=["3 commits, +37/-3", f"{_sha(G, 2)} Attempt to implement API", "Peer ratings 3 and 2"]),
        MemberContribution(student_id="Hank", contribution_score=2, primary_contributions=["Small db/models.py file"],
            evidence=["2 commits, +17/-1", f"{_sha(G, 3)} add models", "Assigned DB-3 (tests) is still To Do"]),
    ],
    executive_summary="In the 2026-08-10 to 2026-08-21 sprint Team_Gamma produced 8 small, late-night commits (+79/-6) touching a DB schema, models and API routes, but finished none of its 3 tickets (0/10 points). There are no tests, no documentation and no CI/CD, commit messages are vague, and peers rate each other 2.67/5 on average.",
    strengths=["Each member committed some code", "Tickets are estimated and assigned"],
    weaknesses=["Zero tickets Done", "No tests, documentation or CI/CD", "Vague commit messages and late-night commits", "Low mutual peer ratings"],
    key_recommendations=["Split DB-1 into tickets small enough to finish and pair on them.", "Write at least one test per feature commit and start DB-3.", "Use descriptive commit messages and commit throughout the sprint.", "Add a README and a basic CI workflow that runs the tests."],
)

# Good collaboration, lower output
D = "Team_Delta"
good_collab_low_output_team = ArtifactBundle(team_id=D, sprint_id=SPRINT_ID, commits=[
    _commit(D, 1, "Ivy", "DEL-1: Add login page skeleton with email/password fields", _ts(11, 10, 3, 12), [
        _file("frontend/src/pages/Login.jsx", "added", 46), _file("frontend/src/App.jsx", "modified", 4, 1)]),
    _commit(D, 2, "Jack", "DEL-2: Style navbar and add mobile breakpoint", _ts(12, 14, 21, 40), [
        _file("frontend/src/components/Navbar.jsx", "added", 31), _file("frontend/src/components/Navbar.css", "added", 38), _file(".DS_Store", "added")]),
    _commit(D, 3, "Kim", "DEL-3: Add client-side email and password validation", _ts(13, 16, 47, 5), [
        _file("frontend/src/utils/validation.js", "added", 34)]),
    _commit(D, 4, "Kim", "DEL-3: Add unit tests for validation helpers", _ts(14, 11, 30, 58), [
        _file("frontend/src/utils/validation.test.js", "added", 41)]),
    _commit(D, 5, "Jack", "Add lint workflow for pull requests", _ts(17, 9, 55, 19), [
        _file(".github/workflows/lint.yml", "added", 22)]),
    _commit(D, 6, "Ivy", "Merge pull request #6 from delta-team/feature/DEL-3-validation", _ts(18, 15, 12, 44), []),
    _commit(D, 7, "Ivy", "Update README with setup steps and component overview", _ts(19, 20, 8, 31), [
        _file("README.md", "modified", 27, 3)]),
], jira_tickets=[
    _ticket("DEL-1", "Build login page", "Ivy", "Done", "Story", 3, _ts(11, 10, 20)),
    _ticket("DEL-2", "Style navbar", "Jack", "Done", "Task", 2, _ts(12, 14, 40)),
    _ticket("DEL-3", "Add form validation", "Kim", "Done", "Task", 3, _ts(18, 15, 15)),
    _ticket("DEL-4", "Connect login form to auth API", "Ivy", "In Progress", "Story", 5, _ts(19, 9, 30)),
], peer_evaluations=[
    PeerEvaluation(evaluator="Ivy", evaluatee="Jack", rating=5, comments="Jack paired with me on the navbar breakpoints and set up the lint check for everyone."),
    PeerEvaluation(evaluator="Ivy", evaluatee="Kim", rating=4, comments="Kim flags blockers early in stand-up, and the validation tests were a nice touch."),
    PeerEvaluation(evaluator="Jack", evaluatee="Ivy", rating=5, comments="Ivy runs our stand-ups and reviews PRs the same day."),
    PeerEvaluation(evaluator="Jack", evaluatee="Kim", rating=4, comments="Kim is thorough and easy to work with, a bit slow to pick up the next ticket."),
    PeerEvaluation(evaluator="Kim", evaluatee="Ivy", rating=4, comments="Very supportive, though the API hookup (DEL-4) slipped because she took on too much."),
    PeerEvaluation(evaluator="Kim", evaluatee="Jack", rating=4, comments="Jack is reliable and gives helpful code review comments."),
])

good_collab_low_output_grade = SprintAssessment(
    team_id=good_collab_low_output_team.team_id, sprint_id=good_collab_low_output_team.sprint_id, prompt_version="v1.0",
    overall_score=6.17,  # (6+6+6+6+8+5)/6
    rubric_scores=RubricsScore(
        code_quality=_dim("code_quality", 6,
            "7 commits (+243/-4) spread evenly across members (Ivy 3, Jack 2, Kim 2), with clear, mostly ticket-keyed messages ('DEL-3: Add client-side email and password validation') and a PR merge (#6). Volume is modest: no commit exceeds +69 lines and the login page is only a skeleton, so contributions are moderate rather than substantial.",
            [_cite(_sha(D, 3), "'DEL-3: Add client-side email and password validation' (+34) is small but clearly described and scoped."),
             _cite(_sha(D, 1), "'DEL-1: Add login page skeleton with email/password fields' (+50/-1) shows the main feature is still a skeleton."),
             _cite(_sha(D, 6), "'Merge pull request #6' shows Kim's validation work was reviewed before merging.")],
            ["Clear, ticket-keyed commit messages", "Even commit distribution across members", "PR-based merge"],
            ["Low code volume for a two-week sprint", "Login page not yet wired to the backend"]),
        testing=_dim("testing", 6,
            "One explicit test commit, 'DEL-3: Add unit tests for validation helpers' (+41, validation.test.js), covers the validation utilities. Login.jsx and Navbar.jsx have no tests, there is no testing ticket, and the lint workflow does not run tests, so coverage is clearly incomplete.",
            [_cite(_sha(D, 4), "'DEL-3: Add unit tests for validation helpers' adds frontend/src/utils/validation.test.js (+41)."),
             _cite("DEL-3", "'Add form validation' is Done and is the only ticket whose work has associated tests."),
             _cite(_sha(D, 1), "'DEL-1: Add login page skeleton…' adds Login.jsx with no component test.")],
            ["Validation helpers are unit tested", "Tests committed separately with a clear message"],
            ["Add component tests for Login and Navbar", "Run tests in the lint workflow"]),
        documentation=_dim("documentation", 6,
            "'Update README with setup steps and component overview' (+27/-3) is a minor but useful README update, and Jira summaries are short but clear ('Connect login form to auth API'). There is no component or API documentation beyond the README.",
            [_cite(_sha(D, 7), "'Update README with setup steps and component overview' modifies README.md (+27/-3)."),
             _cite("DEL-4", "'Connect login form to auth API' clearly states the intended deliverable."),
             _cite("DEL-2", "'Style navbar' is clear but gives no detail on the responsive behaviour delivered.")],
            ["README updated with setup steps", "Readable ticket summaries"],
            ["Document component props and the planned auth API contract", "Add descriptions to Jira tickets"]),
        requirements=_dim("requirements", 6,
            "3 of 4 tickets are Done (DEL-1, DEL-2, DEL-3) for 8 of 13 story points. DEL-4 'Connect login form to auth API' (5 points) is In Progress at sprint end: spillover rather than abandoned, but it is the largest ticket and the one that makes login functional. Most tickets Done but velocity is low, so the bottom of 6-8.",
            [_cite("DEL-1", "'Build login page' (3 points) is Done."),
             _cite("DEL-4", "'Connect login form to auth API' (5 points) is still In Progress, leaving 5 of 13 points undelivered."),
             _cite("DEL-2", "'Style navbar' (2 points) is Done, one of three small tickets completed.")],
            ["Most tickets completed", "All tickets estimated and assigned"],
            ["Prioritise the integration ticket earlier in the sprint", "Commit to more points once velocity is known"]),
        collaboration=_dim("collaboration", 8,
            "Peer ratings average 4.33 (26/30: two 5s, four 4s) with specific, supportive comments about pairing, same-day PR reviews and stand-ups. Workload is mostly balanced by tickets (Ivy 2, Jack 1, Kim 1), although Ivy holds 8 of 13 points, which Kim flags as the reason DEL-4 slipped. Top of band 6-8.",
            [_cite("Ivy -> Jack (5/5)", "'Paired with me on the navbar breakpoints and set up the lint check' shows active pairing."),
             _cite("Jack -> Ivy (5/5)", "'Runs our stand-ups and reviews PRs the same day' shows a working review and stand-up routine."),
             _cite("Kim -> Ivy (4/5)", "'DEL-4 slipped because she took on too much' is honest feedback on workload concentration.")],
            ["Consistently positive, specific peer feedback", "Regular stand-ups and same-day reviews"],
            ["Rebalance points: Ivy holds 8 of 13", "Split large tickets so others can help"]),
        cicd=_dim("cicd", 5,
            "'Add lint workflow for pull requests' adds .github/workflows/lint.yml (+22), so PRs are linted automatically, but the workflow has no test, build or deploy step and is never revisited during the sprint. CI is only partially implemented.",
            [_cite(_sha(D, 5), "'Add lint workflow for pull requests' adds .github/workflows/lint.yml (+22), the only pipeline file."),
             _cite(_sha(D, 4), "validation.test.js exists, but nothing in the bundle shows CI running it."),
             _cite(".github/workflows/lint.yml", "Added once on 08-17 and never updated, so the pipeline did not grow with the code.")],
            ["Automated lint on every PR"],
            ["Add a test step to the workflow", "Add a build step so broken builds are caught"]),
    ),
    member_contributions=[
        MemberContribution(student_id="Ivy", contribution_score=7, primary_contributions=["Login page skeleton (DEL-1)", "README update and PR merge (#6)", "Owns in-progress DEL-4"],
            evidence=["3 commits (1 PR merge), +77/-4", f"{_sha(D, 1)} DEL-1: Add login page skeleton with email/password fields", "Peer ratings 5 and 4"]),
        MemberContribution(student_id="Jack", contribution_score=7, primary_contributions=["Navbar styling (DEL-2)", "Lint workflow for PRs"],
            evidence=["2 commits, +91/-0", f"{_sha(D, 2)} DEL-2: Style navbar and add mobile breakpoint", "Peer ratings 5 and 4"]),
        MemberContribution(student_id="Kim", contribution_score=6, primary_contributions=["Form validation (DEL-3)", "Unit tests for validation helpers"],
            evidence=["2 commits, +75/-0", f"{_sha(D, 4)} DEL-3: Add unit tests for validation helpers", "Peer ratings 4 and 4"]),
    ],
    executive_summary="In the 2026-08-10 to 2026-08-21 sprint Team_Delta collaborated well (peer average 4.33/5, even commits, PR reviews) but produced little: 7 commits (+243/-4) for a login page skeleton, navbar and form validation, with 3 of 4 tickets (8/13 points) Done and the API hookup still In Progress. Testing, documentation and CI are present but thin: one test file, a README update and a lint-only workflow.",
    strengths=["Strong, specific peer feedback and regular stand-ups", "Clear ticket-keyed commits spread across members", "Some testing, documentation and CI from the start"],
    weaknesses=["Low output for a two-week sprint", "Key integration ticket (DEL-4) not finished", "CI runs lint only"],
    key_recommendations=["Prioritise integration work (DEL-4) earlier in the sprint.", "Add component tests and run them in the workflow.", "Rebalance story points so Ivy is not the bottleneck.", "Commit to more points once velocity is established."],
)

# 1 person carry, good outcome
E = "Team_Epsilon"
imbalanced_high_output_team = ArtifactBundle(team_id=E, sprint_id=SPRINT_ID, commits=[
    _commit(E, 1, "Liam", "PAY-1: Add payment processing service with Stripe client wrapper", _ts(10, 9, 12, 44), [
        _file("payments/service.py", "added", 248), _file("payments/models.py", "added", 36), _file("payments/__init__.py", "added", 1)]),
    _commit(E, 2, "Liam", "PAY-2: Handle payment_intent webhooks with signature verification", _ts(13, 13, 15, 2), [
        _file("payments/webhooks.py", "added", 187), _file("tests/test_webhooks.py", "added", 94)]),
    _commit(E, 3, "Liam", "PAY-1: Unit tests for charge, capture and idempotency keys", _ts(15, 23, 58, 31), [
        _file("tests/test_service.py", "added", 132), _file("tests/__pycache__/test_service.cpython-311-pytest-8.2.0.pyc", "added")]),
    _commit(E, 4, "Liam", "PAY-3: Implement refund flow and partial refunds", _ts(17, 1, 26, 49), [
        _file("payments/refunds.py", "added", 164), _file("payments/service.py", "modified", 22, 9)]),
    _commit(E, 5, "Liam", "PAY-4: Add CI pipeline (pytest + coverage), Dockerfile and staging deploy", _ts(18, 19, 3, 37), [
        _file(".github/workflows/ci.yml", "added", 34), _file(".github/workflows/deploy.yml", "added", 41), _file("Dockerfile", "added", 21)]),
    _commit(E, 6, "Liam", "Document payments API, webhook events and refund rules", _ts(19, 21, 47, 10), [
        _file("docs/payments.md", "added", 118), _file("README.md", "modified", 19, 2)]),
    _commit(E, 7, "Maya", "Fix typo in payment config comment", _ts(20, 9, 0, 26), [_file("payments/config.py", "modified", 1, 1)]),
    _commit(E, 8, "Noah", "Update .gitignore", _ts(20, 9, 31, 58), [_file(".gitignore", "modified", 2), _file(".DS_Store", "deleted")]),
], jira_tickets=[
    _ticket("PAY-1", "Payments service", "Liam", "Done", "Story", 8, _ts(16, 0, 5)),
    _ticket("PAY-2", "Webhooks", "Liam", "Done", "Task", 5, _ts(13, 13, 30)),
    _ticket("PAY-3", "Refunds", "Liam", "In Review", "Story", 5, _ts(17, 1, 30)),
    _ticket("PAY-4", "CI/CD", "Liam", "Done", "Task", 3, _ts(18, 19, 10)),
], peer_evaluations=[
    PeerEvaluation(evaluator="Maya", evaluatee="Liam", rating=3, comments="Liam built almost everything, but he pushed straight to main and took over refunds before I could start, without asking."),
    PeerEvaluation(evaluator="Noah", evaluatee="Liam", rating=3, comments="Huge output, but no PRs or stand-up updates, so we never knew what was left to pick up."),
    PeerEvaluation(evaluator="Liam", evaluatee="Maya", rating=1, comments="Maya didn't pick up any ticket this sprint; her only commit was a typo fix."),
    PeerEvaluation(evaluator="Liam", evaluatee="Noah", rating=1, comments="Noah's only change was .gitignore. I had to do the webhooks and refunds myself."),
    PeerEvaluation(evaluator="Maya", evaluatee="Noah", rating=2, comments="Noah was rarely online and missed both stand-ups."),
    PeerEvaluation(evaluator="Noah", evaluatee="Maya", rating=2, comments="Maya said she would take refunds but never pushed anything."),
])

imbalanced_high_output_grade = SprintAssessment(
    team_id=imbalanced_high_output_team.team_id, sprint_id=imbalanced_high_output_team.sprint_id, prompt_version="v1.0",
    overall_score=6.67,  # (8+7+7+8+2+8)/6
    rubric_scores=RubricsScore(
        code_quality=_dim("code_quality", 8,
            "8 commits (+1,120/-12) deliver a full payments service (charge/capture, signed webhooks, refunds) with descriptive, ticket-keyed messages. Held below 9 because 6 of 8 commits are large single-author drops by Liam (up to +285) pushed straight to main with no PR merges, and the other two commits are trivial (a typo fix, a .gitignore line).",
            [_cite(_sha(E, 1), "'PAY-1: Add payment processing service with Stripe client wrapper' (+285) is substantial but lands as one large drop."),
             _cite(_sha(E, 2), "'PAY-2: Handle payment_intent webhooks with signature verification' (+281) ships the feature with its tests."),
             _cite(_sha(E, 7), "'Fix typo in payment config comment' (+1/-1) is Maya's only commit, a trivial change.")],
            ["Substantial, working payments functionality", "Descriptive ticket-keyed commit messages"],
            ["Break large drops into reviewable PRs", "No PR merges: everything pushed straight to main", "Commits at 23:58 and 01:26 suggest crunch"]),
        testing=_dim("testing", 7,
            "Two explicit test commits add 226 test lines: tests/test_webhooks.py ships with the webhook handler, and 'PAY-1: Unit tests for charge, capture and idempotency keys' adds tests/test_service.py (+132). CI runs pytest with coverage. Gaps: the refund flow (PAY-3, +186/-9) has no tests and there is no dedicated testing ticket.",
            [_cite(_sha(E, 3), "'PAY-1: Unit tests for charge, capture and idempotency keys' adds tests/test_service.py (+132)."),
             _cite(_sha(E, 2), "The webhook commit includes tests/test_webhooks.py (+94) alongside payments/webhooks.py."),
             _cite(_sha(E, 4), "'PAY-3: Implement refund flow and partial refunds' (+186/-9) adds no test file.")],
            ["Service and webhook logic unit tested", "Coverage measured in CI"],
            ["Add tests for refunds and partial refunds", "Create a testing ticket so coverage is planned"]),
        documentation=_dim("documentation", 7,
            "Explicit documentation commit 'Document payments API, webhook events and refund rules' adds docs/payments.md and updates README.md (+137/-2). However, Jira summaries are one- or two-word labels ('Webhooks', 'Refunds', 'CI/CD') that do not document the work, so this falls short of the 9-10 band.",
            [_cite(_sha(E, 6), "'Document payments API, webhook events and refund rules' adds docs/payments.md and updates README.md (+137/-2)."),
             _cite("PAY-2", "'Webhooks' is a one-word summary that does not describe which events or verification were delivered."),
             _cite("PAY-4", "'CI/CD' gives no detail on the pipeline stages the ticket delivered.")],
            ["Dedicated API documentation file", "README updated"],
            ["Write descriptive Jira summaries", "Documentation written by one member only; others should review it"]),
        requirements=_dim("requirements", 8,
            "3 of 4 tickets are Done (PAY-1, PAY-2, PAY-4) for 16 of 21 story points, and PAY-3 'Refunds' (5 points) is In Review rather than stuck. Strong velocity for one sprint, but every ticket is assigned to one member and the open review on refunds keeps this below 9-10.",
            [_cite("PAY-1", "'Payments service' (8 points) is Done, the largest delivered ticket."),
             _cite("PAY-3", "'Refunds' (5 points) is In Review at sprint end, not yet Done."),
             _cite("PAY-2", "'Webhooks' (5 points) is Done.")],
            ["High story-point velocity (16/21)", "No abandoned tickets"],
            ["Finish the refund review", "Assign tickets to all three members"]),
        collaboration=_dim("collaboration", 2,
            "Peer ratings average 2.0 (12/30). Liam receives 3s for output but poor communication ('pushed straight to main'), while Maya and Noah receive only 1s and 2s for not picking up work. All 4 tickets (21 points) are assigned to Liam and Maya and Noah hold none, which is strong evidence of freeriding.",
            [_cite("Liam -> Maya (1/5)", "'Didn't pick up any ticket this sprint' documents a member with no assigned work."),
             _cite("Noah -> Liam (3/5)", "'No PRs or stand-up updates' shows the high performer did not coordinate with the team."),
             _cite("PAY-4", "Even the CI/CD ticket is Liam's; Maya and Noah are assigned 0 of 4 tickets.")],
            ["Liam's delivery is acknowledged by both teammates"],
            ["Assign tickets to every member at planning", "Use PRs and stand-ups so work is visible and shared"]),
        cicd=_dim("cicd", 8,
            "'PAY-4: Add CI pipeline (pytest + coverage), Dockerfile and staging deploy' adds .github/workflows/ci.yml, .github/workflows/deploy.yml and a Dockerfile, covering automated tests, image build and deployment to staging. Minor gap: the pipeline arrives on day 9 of 12 in one commit, so most features were pushed before any automated check existed.",
            [_cite(_sha(E, 5), "'PAY-4: Add CI pipeline (pytest + coverage), Dockerfile and staging deploy' adds ci.yml, deploy.yml and a Dockerfile (+96)."),
             _cite(".github/workflows/deploy.yml", "A deploy-to-staging workflow (+41) means the team has CD, not just CI."),
             _cite(_sha(E, 1), "'PAY-1: Add payment processing service…' (+285) landed eight days before any CI check existed.")],
            ["Test, build and staging deploy all automated", "Coverage reported in CI"],
            ["Set up CI at the start of the sprint", "Require CI to pass on PRs before merging"]),
    ),
    member_contributions=[
        MemberContribution(student_id="Liam", contribution_score=9,
            primary_contributions=["Payments service, webhooks and refunds (PAY-1 to PAY-3)", "CI, Docker and staging deploy (PAY-4)", "Payments documentation"],
            evidence=["6 commits, +1,117/-11", f"{_sha(E, 1)} PAY-1: Add payment processing service with Stripe client wrapper", "Peer ratings 3 and 3 (communication concerns)"]),
        MemberContribution(student_id="Maya", contribution_score=2, primary_contributions=["One-line comment typo fix"],
            evidence=["1 commit, +1/-1", f"{_sha(E, 7)} Fix typo in payment config comment", "0 Jira tickets assigned"]),
        MemberContribution(student_id="Noah", contribution_score=2, primary_contributions=[".gitignore update"],
            evidence=["1 commit, +2/-0", f"{_sha(E, 8)} Update .gitignore", "0 Jira tickets assigned"]),
    ],
    executive_summary="In the 2026-08-10 to 2026-08-21 sprint Team_Epsilon shipped a payments service with signed webhooks, refunds, unit tests, documentation and a CI/CD pipeline (8 commits, +1,120/-12; 16/21 points Done). Almost all of it is Liam's: he authored 6 of 8 commits and every ticket, while Maya and Noah made one trivial commit each. Peer ratings average 2.0/5, reflecting freeriding and no PR or stand-up communication.",
    strengths=["High output with ticket-keyed commits", "Automated test, build and staging deploy", "Documented payments API"],
    weaknesses=["One member carried the whole sprint", "No PRs or code review", "Refunds untested; CI added late"],
    key_recommendations=["Assign every member tickets at sprint planning and track them on the board.", "Require PRs with at least one reviewer instead of pushing to main.", "Add refund tests and set up CI at the start of each sprint.", "Pair Maya and Noah with Liam to spread knowledge of the payments code."],
)

# Only 1 person did any work, and the outcome was still poor
T = "Team_Theta"
lone_contributor_poor_outcome_team = ArtifactBundle(team_id=T, sprint_id=SPRINT_ID, commits=[
    _commit(T, 1, "Uma", "REP-1: Add report generator core (CSV rows from orders table)", _ts(12, 20, 3, 27), [
        _file("reports/generator.py", "added", 112), _file("reports/__init__.py", "added", 1)]),
    _commit(T, 2, "Uma", "REP-1: Add query helpers for report filters", _ts(13, 23, 41, 56), [
        _file("reports/queries.py", "added", 58), _file(".DS_Store", "added")]),
    _commit(T, 3, "Uma", "WIP export", _ts(15, 22, 19, 8), [_file("reports/export.py", "added", 74)]),
    _commit(T, 4, "Uma", "WIP, ran out of time", _ts(17, 23, 30, 45), [_file("reports/export.py", "modified", 18, 4)]),
    _commit(T, 5, "Uma", "add basic test", _ts(18, 22, 52, 11), [
        _file("tests/test_generator.py", "added", 16), _file("tests/__pycache__/test_generator.cpython-311-pytest-8.2.0.pyc", "added")]),
    _commit(T, 6, "Uma", "Add Dockerfile", _ts(19, 1, 7, 39), [_file("Dockerfile", "added", 12), _file(".dockerignore", "added", 3)]),
    _commit(T, 7, "Uma", "Partial fix for report export bug + readme", _ts(20, 22, 10, 33), [
        _file("reports/export.py", "modified", 15, 3), _file("README.md", "added", 5)]),
], jira_tickets=[
    _ticket("REP-1", "Build report generation core", "Uma", "Done", "Story", 5, _ts(13, 23, 50)),
    _ticket("REP-2", "Add report export (PDF/CSV)", "Uma", "In Progress", "Story", 5, _ts(15, 22, 20)),
    _ticket("REP-3", "Add report scheduling", "Victor", "To Do", "Task", 3, _ts(10, 9, 0)),
    _ticket("REP-4", "Add report access permissions", "Wei", "To Do", "Task", 2, _ts(10, 9, 0)),
], peer_evaluations=[
    PeerEvaluation(evaluator="Uma", evaluatee="Victor", rating=1, comments="Victor never started REP-3 and stopped replying in the group chat after week one."),
    PeerEvaluation(evaluator="Uma", evaluatee="Wei", rating=1, comments="Wei joined the planning call but wrote no code and left REP-4 in To Do."),
    PeerEvaluation(evaluator="Victor", evaluatee="Uma", rating=3, comments="Uma did all the coding, but she worked alone at night and never split the export work."),
    PeerEvaluation(evaluator="Victor", evaluatee="Wei", rating=1, comments="Wei didn't do anything I could see."),
    PeerEvaluation(evaluator="Wei", evaluatee="Uma", rating=3, comments="Uma carried the whole feature alone and it was too much for one person."),
    PeerEvaluation(evaluator="Wei", evaluatee="Victor", rating=2, comments="Victor said he'd do scheduling but nothing happened."),
])

lone_contributor_poor_outcome_grade = SprintAssessment(
    team_id=lone_contributor_poor_outcome_team.team_id, sprint_id=lone_contributor_poor_outcome_team.sprint_id, prompt_version="v1.0",
    overall_score=3.33,  # (5+3+3+4+1+4)/6
    rubric_scores=RubricsScore(
        code_quality=_dim("code_quality", 5,
            "All 7 commits (+314/-7) are by Uma. The report generator core (+113) and query helpers (+58) are real work, but export is committed as 'WIP export' and 'WIP, ran out of time' and ends in a 'Partial fix', and 6 of 7 commits land after 22:00. Moderate volume with vague messages puts this at the top of band 3-5.",
            [_cite(_sha(T, 1), "'REP-1: Add report generator core (CSV rows from orders table)' (+113) is the sprint's one substantive, well-described commit."),
             _cite(_sha(T, 4), "'WIP, ran out of time' (+18/-4) is an unhelpful message for unfinished export code."),
             _cite(_sha(T, 7), "'Partial fix for report export bug + readme' mixes an incomplete fix with unrelated docs in one commit.")],
            ["Working report generator core", "Early commits are clearly described"],
            ["Replace 'WIP' messages with descriptive ones", "Keep unrelated changes in separate commits", "Other members committed nothing"]),
        testing=_dim("testing", 3,
            "One test commit, 'add basic test', adds a 16-line tests/test_generator.py. Nothing tests export (the buggy module) or the query helpers, and no Jira ticket covers testing. Minimal testing evidence.",
            [_cite(_sha(T, 5), "'add basic test' adds only tests/test_generator.py (+16), the sprint's single test file."),
             _cite(_sha(T, 7), "'Partial fix for report export bug' changes export.py with no regression test."),
             _cite("REP-2", "'Add report export (PDF/CSV)' is In Progress and has no testing evidence.")],
            ["A first test exists for the generator"],
            ["Test export before fixing its bug", "Plan testing as a ticket"]),
        documentation=_dim("documentation", 3,
            "The only documentation is a 5-line README.md bundled into 'Partial fix for report export bug + readme'. There are no docs/ files, no documentation ticket, and Jira summaries name deliverables but carry no detail. Documentation exists only as a stub.",
            [_cite(_sha(T, 7), "README.md is added with only 5 lines, inside an unrelated bug-fix commit."),
             _cite("REP-1", "'Build report generation core' names the deliverable but does not document how reports are generated."),
             _cite("REP-3", "'Add report scheduling' has no description of the intended behaviour.")],
            ["A README was started"],
            ["Document report formats and how to run the generator", "Add descriptions to Jira tickets"]),
        requirements=_dim("requirements", 4,
            "1 of 4 tickets is Done (REP-1, 5 of 15 points). REP-2 export (5 points) is In Progress, and REP-3 scheduling (Victor) and REP-4 access permissions (Wei) were never started. Fewer than half Done with low velocity puts this in band 3-5; kept above 3 because the core report feature was delivered.",
            [_cite("REP-1", "'Build report generation core' (5 points) is the only Done ticket."),
             _cite("REP-3", "'Add report scheduling' (3 points, Victor) never left To Do."),
             _cite("REP-4", "'Add report access permissions' (2 points, Wei) never left To Do.")],
            ["Core report generation delivered"],
            ["Re-plan REP-3 and REP-4 with owners who will start them", "Finish REP-2 before taking new work"]),
        collaboration=_dim("collaboration", 1,
            "Peer ratings average 1.83 (11/30). Victor and Wei receive only 1s and 2s, and neither started their assigned tickets (REP-3 and REP-4 are still To Do), while Uma holds 10 of 15 points. Even Uma's 3/5 ratings note she worked alone ('never split the export work'). Strong evidence of freeriding.",
            [_cite("Uma -> Victor (1/5)", "'Never started REP-3 and stopped replying' documents a disengaged member."),
             _cite("REP-4", "Wei's only ticket is still To Do, matching 'wrote no code' in Uma's evaluation."),
             _cite("Wei -> Uma (3/5)", "'Carried the whole feature alone' confirms the work was not shared.")],
            [],
            ["Hold regular stand-ups and escalate non-participation early", "Split large tickets so work can be shared"]),
        cicd=_dim("cicd", 4,
            "'Add Dockerfile' adds a Dockerfile and .dockerignore (+15), so the app can be containerised, but no workflow, pipeline or deploy configuration exists in any of the 7 commits and the Dockerfile is never revisited. Containerisation only, so CI/CD is partial.",
            [_cite(_sha(T, 6), "'Add Dockerfile' adds Dockerfile and .dockerignore (+15), the only build-automation work."),
             _cite(_sha(T, 5), "'add basic test' adds a test, but nothing in the bundle runs it automatically."),
             _cite(_sha(T, 7), "The last commit changes export.py with no pipeline to check the fix.")],
            ["App containerised"],
            ["Add a CI workflow that runs the tests", "Build the Docker image in CI"]),
    ),
    member_contributions=[
        MemberContribution(student_id="Uma", contribution_score=6,
            primary_contributions=["Report generator core and query helpers (REP-1)", "Partial export (REP-2)", "Dockerfile, one test and a README stub"],
            evidence=["7 of 7 commits, +314/-7", f"{_sha(T, 1)} REP-1: Add report generator core (CSV rows from orders table)", "Peer ratings 3 and 3"]),
        MemberContribution(student_id="Victor", contribution_score=1, primary_contributions=["No recorded contribution"],
            evidence=["0 commits", "REP-3 still To Do", "Peer ratings 1 and 2"]),
        MemberContribution(student_id="Wei", contribution_score=1, primary_contributions=["Attended sprint planning only"],
            evidence=["0 commits", "REP-4 still To Do", "Peer ratings 1 and 1"]),
    ],
    executive_summary="In the 2026-08-10 to 2026-08-21 sprint only Uma contributed to Team_Theta: all 7 commits (+314/-7), delivering the report generator core but leaving export partial (WIP commits, a partial bug fix). 1 of 4 tickets (5/15 points) is Done, Victor and Wei never started their tickets, testing and documentation are minimal, and CI/CD is limited to a Dockerfile. Peers rate each other 1.83/5 on average.",
    strengths=["Report generator core delivered", "Uma's sustained effort"],
    weaknesses=["Two members contributed nothing", "Export unfinished and buggy", "Minimal tests and documentation; no pipeline"],
    key_recommendations=["Escalate Victor's and Wei's non-participation to the instructor early in the next sprint.", "Re-plan REP-3 and REP-4 and pair each with Uma for handover.", "Add tests for export before fixing its bug.", "Add a CI workflow that runs the tests and builds the Dockerfile."],
)

ALPHA_GOLD = SprintAssessment.model_validate_json(
    (DATA_DIR / "gold" / "alpha_GOLD.json").read_text()
)

GAMMA_GOLD = SprintAssessment.model_validate_json(
    (DATA_DIR / "gold" / "gamma_GOLD.json").read_text()
)

DELTA_GOLD = SprintAssessment.model_validate_json(
    (DATA_DIR / "gold" / "delta_GOLD.json").read_text()
)

EPSILON_GOLD = SprintAssessment.model_validate_json(
    (DATA_DIR / "gold" / "epsilon_GOLD.json").read_text()
)

THETA_GOLD = SprintAssessment.model_validate_json(
    (DATA_DIR / "gold" / "theta_GOLD.json").read_text()
)

FIXTURES_TEAMS = (
    high_performing_team,
    good_collab_low_output_team,
    imbalanced_high_output_team,
    lone_contributor_poor_outcome_team,
    struggling_team,
)

FIXTURES_GOLD = {
    "team_alpha": ALPHA_GOLD,
    "team_gamma": GAMMA_GOLD,
    "team_delta": DELTA_GOLD,
    "team_epsilon": EPSILON_GOLD,
    "team_theta": THETA_GOLD,
}
