from pathlib import Path

from schemas.artifact_bundle import ArtifactBundle
from schemas.member_contribution import MemberContribution
from schemas.rubrics_score import RubricDimensionScore, RubricsScore
from schemas.sprint_assessment import SprintAssessment


# Citations must be dicts: ModelOutput.coerce_citations mangles EvidenceCitation objects
# (identifier=str(obj), reason="") and then fails the 15-char reason minimum.
def cite(identifier: str, reason: str) -> dict:
    return {"identifier": identifier, "reason": reason}

CS203G6_BUNDLE = ArtifactBundle.model_validate_json(
    (Path(__file__).resolve().parent.parent / "research" / "cs203g6_AB.json").read_text()
)

CS203G6_GOLD = SprintAssessment(
    sprint_id="2024-11-13_to_2024-11-24",
    team_id="cs203g6",
    prompt_version="v1.0",
    overall_score=4.0,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality", score=4,
            justification="31 commits (+2,185/-3,901) include one real refactor of the tournament draw algorithm, but most messages are non-descriptive ('deploy 6', 'tete', 'djsjds', '.') and some mislead: the commit titled 'Added explanations for draw algo and refactored code' deletes 1,184 lines including the whole Highlight module. A binary users.mv.db was also committed twice.",
            evidence_citations=[
                cite("7373c90c578ff7614f8c0a3ecac58a4ccba1cd4b", "'Refactored draw algo code in tournament service impl' is the clearest substantive commit (+105/-7 in TournamentServiceImpl.java)."),
                cite("1fa521707d37e0774df170c4b7d4d2c9af1aecdd", "Message says 'Added explanations' but the diff deletes 1,184 lines, including Highlight.java and six test files."),
                cite("f7053a0966d995e061d856b9d6aa7667f5f0e98f", "'djsjds' is a meaningless message for a one-line loginAPI.js change, typical of trial-and-error committing."),
            ],
            strengths=["One substantive refactor of the tournament draw algorithm (+105/-7)", "Dockerfiles added for both backend and frontend"],
            areas_for_improvement=["Squash 'deploy N' / 'update deploy N' chains into descriptive commits", "Make messages match diffs (1fa5217 hides a 1,184-line deletion)", "Do not commit the H2 database file backend/data/users.mv.db or repeatedly hand-edit environment values across six frontend API files"],
        ),
        testing=RubricDimensionScore(
            dimension="testing", score=4,
            justification="Five integration test classes (~980 lines, incl. SpringBootIntegrationTest.java) are added in dabe40d, but under the message 'refactor', after 1fa5217 had deleted five test files and removed 199 lines from TournamentServiceTest. accdb19 then rewrote them (+478/-980). No commit is explicitly about testing, there are no test tickets, and no CI test step is visible in the bundle.",
            evidence_citations=[
                cite("dabe40df151737b92d0ef905636cb0bfed1e4945", "'refactor' commit adds five integration test files (SpringBootIntegrationTest.java alone +396) with no test-related message."),
                cite("1fa521707d37e0774df170c4b7d4d2c9af1aecdd", "Deletes AdminIntegrationTest, HighlightServiceTest and three more test files, so the suite was wiped before being re-added."),
                cite("accdb1920434a326e8d3cef6ae0bb739af33918e", "'consolidated files' rewrites the integration tests (+478/-980), shrinking net test code."),
            ],
            strengths=["Backend has unit-style (MatchServiceTest, TournamentServiceTest) and integration test classes", "Integration tests cover admin, player, tournament and user flows"],
            areas_for_improvement=["Name test commits explicitly and keep tests with the feature commits", "Avoid deleting then re-adding the whole suite", "Add test tickets, a CI test stage and coverage reporting"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation", score=3,
            justification="No README, docs or API-documentation file is touched by any of the 31 commits. The only documentation effort is 1fa5217, which adds 6 lines of inline explanation to the draw algorithm in TournamentServiceImpl.java. Commit messages ('deploy 6', 'tete', '.') carry almost no information and there are no Jira tickets recording intent.",
            evidence_citations=[
                cite("1fa521707d37e0774df170c4b7d4d2c9af1aecdd", "'Added explanations for draw algo' is the only documentation-oriented change (+6/-2 in TournamentServiceImpl.java)."),
                cite("9fe6420993403357b5f0aca62600ca3171dc4710", "Message '.' covers changes to docker-compose.yaml, dockerfile, pom.xml and application.properties with no explanation."),
                cite("1fa222c78ec034634f2b2144f1fa3c540299d9fc", "'tete' is an uninformative message for a WebConfig.java change."),
            ],
            strengths=["The draw algorithm received inline explanatory comments"],
            areas_for_improvement=["Add a README with setup, Docker and deployment steps (deploy.yml, ecs-task-def.json)", "Use descriptive commit messages (scope + intent)", "Document config and environment changes alongside the pipeline"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements", score=3,
            justification="The bundle has no Jira tickets, story points or ticket keys in commit messages, so no requirement can be traced or confirmed Done. Visible work is a draw-algorithm refactor, a deployment pipeline and test rework, but 1fa5217 also deletes the whole Highlight feature (six files) with no recorded requirement. Scored conservatively because completion cannot be inferred.",
            evidence_citations=[
                cite("jira_tickets: []", "Empty Jira feed: no tickets, story points or sprint plan to measure completion against."),
                cite("7373c90c578ff7614f8c0a3ecac58a4ccba1cd4b", "The draw-algorithm refactor is the only clearly feature-oriented change and has no ticket reference."),
                cite("1fa521707d37e0774df170c4b7d4d2c9af1aecdd", "Deletes Highlight.java, HighlightController.java and four related files with no stated requirement."),
            ],
            strengths=["Visible progress on deployment, Docker and tournament logic"],
            areas_for_improvement=["Track sprint goals and tickets in Jira with IDs in commit messages", "Record acceptance criteria and a definition of done", "Justify feature removals (Highlight module) through a ticket"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration", score=4,
            justification="No peer evaluations were supplied. Student3 authored 20 of 31 commits (65%, mostly deployment micro-fixes), Student1 8 and Student2 only 3 (+111 lines), so workload is highly imbalanced. Both merges (3056479, b970c95) are plain 'Merge branch main' commits with no pull-request or review trail, though all three members did contribute.",
            evidence_citations=[
                cite("peer_evaluations: []", "Empty list means the peer-rating criterion cannot be applied, so the score is conservative."),
                cite("3056479e93828170579a15ca9ada142c349294d5", "Merge of 'main' integrates parallel work directly, with no PR or review evidence."),
                cite("b970c955d2b56be8ed72b977a5bd34695d65f643", "Second direct merge (+214/-1,325) combining all three authors' changes, again with no review trail."),
            ],
            strengths=["All three members committed in the window", "Student1 and Student3 reconciled concurrent work through merges"],
            areas_for_improvement=["Rebalance work: Student3 has 65% of commits, Student2 under 10%", "Use PRs with required reviews instead of direct merges", "Collect peer evaluations to judge contribution fairness"],
        ),
        cicd=RubricDimensionScore(
            dimension="cicd", score=6,
            justification="A GitHub Actions to ECS deployment pipeline exists: .github/workflows/deploy.yml is edited in 9 commits within ~80 minutes, ecs-task-def.json is added in 4def018 and tuned in 86ce982 and d824813, plus Dockerfiles and docker-compose.yaml. It was built by trial and error ('deploy 6' to 'deploy 11', then repeated frontend URL fixes) and the bundle shows no automated test stage, so it is present but with gaps.",
            evidence_citations=[
                cite("55900130f180e470aa9fb1be1a27f9315a973464", "'update deploy.yml' (+43/-43) starts the rework of .github/workflows/deploy.yml, the CI/CD workflow."),
                cite("4def0186e835f3ec5926ad230577d4f15ef94d64", "'update 7' adds ecs-task-def.json (+31), the container task definition used for deployment."),
                cite("df7101244e88bb28e426885323e392799106ca1e", "'deploy 11' is the ninth workflow edit in ~80 minutes, showing responsiveness to failing runs but no stable first pass."),
            ],
            strengths=["Automated deploy workflow and ECS task definition created in one afternoon", "Both frontend and backend containerised (dockerfile, docker-compose.yaml)", "Iterated quickly on failing deployments"],
            areas_for_improvement=["No evidence in the bundle of an automated test or build-verification stage", "Environment URLs re-edited across six frontend API files (deploy 15, deploy 18) instead of using env variables", "Validate the workflow on a branch and squash trial-and-error commits"],
        ),
    ),
    member_contributions=[
        MemberContribution(student_id="Student3", contribution_score=6,
            primary_contributions=["Owned the GitHub Actions deploy workflow and ECS task definition", "Repeated deployment and API-URL fixes in WebConfig.java and the frontend API files"],
            evidence=["20 of 31 commits, +170/-201", "55900130f180e470aa9fb1be1a27f9315a973464 update deploy.yml", "Messages like 'deploy 6' and 'djsjds' are non-descriptive"]),
        MemberContribution(student_id="Student1", contribution_score=7,
            primary_contributions=["Added backend and frontend Dockerfiles and docker-compose.yaml", "Re-created and consolidated the integration test suite", "Merged parallel work (b970c95)"],
            evidence=["8 commits, +1,904/-2,435", "dabe40df151737b92d0ef905636cb0bfed1e4945 refactor (+1,037, five integration test files)", "Vague messages 'tete', '.', 'refactor'"]),
        MemberContribution(student_id="Student2", contribution_score=4,
            primary_contributions=["Refactored the tournament draw algorithm in TournamentServiceImpl.java", "Added inline explanations for the draw algorithm"],
            evidence=["3 commits, +111/-1,265", "7373c90c578ff7614f8c0a3ecac58a4ccba1cd4b Refactored draw algo code in tournament service impl", "1fa521707d37e0774df170c4b7d4d2c9af1aecdd also deletes the Highlight module and six test files"]),
    ],
    executive_summary="In the inferred 2024-11-13 to 2024-11-24 window (31 commits, +2,185/-3,901) the team refactored the tournament draw algorithm, containerised the app and built a GitHub Actions/ECS deployment pipeline. Quality gates are weak: most commit messages are non-descriptive, the test suite was deleted and re-added, documentation is nearly absent, and there are no Jira tickets or peer evaluations. Work is concentrated in Student3 (20 of 31 commits).",
    key_recommendations=[
        "Adopt enforced commit/PR standards: descriptive messages, squash 'deploy N' chains, and at least one reviewer before merging to main.",
        "Track work in Jira with issue keys in commit messages and acceptance criteria, including for removals such as the Highlight module.",
        "Add a CI test stage to deploy.yml and keep the integration tests stable instead of deleting and re-adding them.",
        "Write a README covering setup, Docker and the ECS deployment, and keep it in sync with pipeline changes.",
        "Rebalance ownership so Student2 and Student1 share deployment and test work currently carried by Student3.",
    ],
)

CS203JY_BUNDLE = ArtifactBundle.model_validate_json(
    (Path(__file__).resolve().parent.parent / "research" / "cs203jy_AB.json").read_text()
)

CS203JY_GOLD = SprintAssessment.model_validate_json(
    (Path(__file__).resolve().parent.parent / "research" / "gold" /"cs203jy_GOLD.json").read_text()
)

CS203_GOLD = {
    CS203G6_GOLD.team_id.lower(): CS203G6_GOLD,
    CS203JY_GOLD.team_id.lower(): CS203JY_GOLD,
}