from prompts.dimension_criteria import DIMENSIONS
from schemas.fixtures import (
    good_collab_low_output_team,
    high_performing_team,
    imbalanced_high_output_team,
    lone_contributor_poor_outcome_team,
    struggling_team,
)
from schemas.rubrics_dimension_score import EvidenceCitation, RubricDimensionScore
from schemas.rubrics_score import RubricsScore
from schemas.sprint_assessment import SprintAssessment


def _cite(text: str) -> EvidenceCitation:
    """Wrap a hand-authored benchmark citation sentence as an EvidenceCitation --
    reused for both `identifier` and `reason` since these gold citations are
    already full sentences, not the (identifier, reason) pairs a real model
    produces."""
    return EvidenceCitation(identifier=text, reason=text)


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