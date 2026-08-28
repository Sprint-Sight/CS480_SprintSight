from schemas.sprint_assessment import SprintAssessment
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.member_contribution import MemberContribution
from schemas.rubrics_score import RubricsScore
from schemas.fixtures import (
    high_performing_team, struggling_team, good_collab_low_output_team,
    imbalanced_high_output_team, lone_contributor_poor_outcome_team,
)

high_performing_grade = SprintAssessment(
    team_id=high_performing_team.team_id,
    sprint_id=high_performing_team.sprint_id,
    prompt_version="v1.0",
    overall_score=9,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=9,
            justification="Commits are small and single-purpose across all three members, with no large untested diffs.",
            evidence_citations=[
                "Charlie's 'Refactor auth service for performance' commit is a focused +80/-20 change.",
                "Alice's 'Fix bug in auth token refresh' commit is a targeted +30/-2 fix.",
            ],
            strengths=["Small, focused commits", "Clear one-concern-per-commit pattern"],
            areas_for_improvement=["Commit messages don't reference Jira ticket IDs directly"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=8,
            justification="A dedicated testing ticket was completed alongside the feature it covers.",
            evidence_citations=[
                "Jira ticket AUTH-2 'Auth Tests' is marked Done, assigned to Bob.",
                "Bob's 'Write unit tests for auth' commit added 120 lines to the new tests/test_auth.py.",
            ],
            strengths=["Testing tracked as its own ticket, not an afterthought"],
            areas_for_improvement=["No coverage percentage is visible from the artifacts"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=8,
            justification="Documentation was planned and delivered as its own ticket.",
            evidence_citations=[
                "Jira ticket AUTH-5 'Auth Documentation' is marked Done.",
                "Bob's 'Update auth documentation' commit added 50 lines to docs/auth.md.",
            ],
            strengths=["Documentation given its own ticket and commit"],
            areas_for_improvement=["No README or architecture diagram referenced in the artifacts"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=9,
            justification="All 6 planned Jira tickets for the sprint are marked Done.",
            evidence_citations=[
                "Jira tickets AUTH-1 through AUTH-6 are all marked Done.",
                "19 story points were planned and fully delivered.",
            ],
            strengths=["100% ticket completion for the sprint"],
            areas_for_improvement=["Story point estimates aren't validated against actual effort"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=10,
            justification="All 6 peer evaluations gave the maximum rating with specific, substantive comments.",
            evidence_citations=[
                "Bob rated Alice 5/5: 'Alice crushed it!'",
                "Charlie rated Bob 5/5: 'Bob's documentation updates were clear and helpful.'",
            ],
            strengths=["Every teammate gave specific, positive feedback about a teammate"],
            areas_for_improvement=["No constructive critique appears anywhere in peer feedback"],
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
    overall_score=3,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=5,
            justification="Commits are small and iterative, and one message signals outright uncertainty about the approach.",
            evidence_citations=[
                "Frank's commit message 'Attempt to implement API' signals low confidence in the implementation.",
                "No commit in this sprint exceeds 30 lines, indicating slow, tentative progress.",
            ],
            strengths=["The team iterated on issues (e.g. 'Fix DB schema') rather than abandoning the code"],
            areas_for_improvement=["Commit messages suggest the team is unsure whether its approach works", "Progress is slow relative to sprint length"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=2,
            justification="Some testing activity occurred but the dedicated testing ticket was never closed.",
            evidence_citations=[
                "Jira ticket DB-3 'Write DB Tests' is still marked To Do despite two related commits.",
                "Hank's testing commits total only 12 lines across the sprint.",
            ],
            strengths=["Testing work was started even though the ticket wasn't formally closed"],
            areas_for_improvement=["The dedicated testing ticket (DB-3) was never marked Done", "Test coverage appears minimal given only 12 lines of test code"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=2,
            justification="No documentation work was planned or delivered this sprint.",
            evidence_citations=[
                "No Jira ticket in this sprint addresses documentation.",
                "None of the 6 commits touch a docs/ or README file — all changes are to db/schema.py, api/routes.py, or tests/test_db.py.",
            ],
            strengths=["Commit messages, while terse, do describe what each change does"],
            areas_for_improvement=["No documentation work exists for the DB schema design, the sprint's main focus"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=2,
            justification="Zero of the 3 planned tickets reached Done status by sprint end.",
            evidence_citations=[
                "None of the 3 planned Jira tickets (DB-1, DB-2, DB-3) reached Done status.",
                "DB-1 'Design DB' is still In Progress despite two related commits from Greg.",
            ],
            strengths=["DB-1 did progress from not-started to In Progress"],
            areas_for_improvement=["Zero of 3 planned tickets were completed", "All 10 planned story points remain undelivered"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=4,
            justification="Peer feedback is uniformly mediocre across all three members, indicating broad underperformance rather than one blocker.",
            evidence_citations=[
                "All 6 peer evaluations this sprint rate teammates 2 or 3 out of 5, with no rating above 3.",
                "Hank rated Greg 2/5 ('Greg didn't contribute much') while Greg rated Hank 3/5 ('Hank was not proactive').",
            ],
            strengths=["Feedback, while critical, is specific rather than hostile"],
            areas_for_improvement=["No team member received a rating above 3/5 from any peer", "The team should discuss blockers directly rather than only surfacing them in peer evaluations"],
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
    overall_score=6,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=6,
            justification="Commits are small and clean, but there are only 4 of them across the whole sprint.",
            evidence_citations=[
                "Ivy's 'Add login page skeleton' commit is a focused +35/-2 change.",
                "Kim's 'Add basic form validation' commit is a targeted +40/-5 change.",
            ],
            strengths=["Every commit is small and single-purpose"],
            areas_for_improvement=["Only 4 commits total for a 3-person team across the sprint"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=5,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                "None of the 4 commits touch a tests/ file — changes are to auth/login_page.py, components/navbar.css, and forms/validation.py only.",
            ],
            strengths=["No untested large features were rushed out"],
            areas_for_improvement=["No dedicated testing ticket or commit exists this sprint"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=5,
            justification="No dedicated documentation ticket or commit exists, though ticket summaries are clear.",
            evidence_citations=[
                "Jira ticket summaries (DEL-1 through DEL-4) are short but clear.",
            ],
            strengths=["Ticket summaries are unambiguous"],
            areas_for_improvement=["No README or user-facing documentation was produced"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=5,
            justification="Only 2 of 4 planned tickets are Done; the other 2 are still In Progress or To Do.",
            evidence_citations=[
                "Jira tickets DEL-1 and DEL-2 are marked Done.",
                "Jira ticket DEL-3 is still In Progress and DEL-4 is still To Do.",
            ],
            strengths=["The 2 completed tickets were fully finished, not left half-done"],
            areas_for_improvement=["Half of the sprint's planned tickets did not reach Done"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=9,
            justification="All 6 peer evaluations rate teammates 4 or 5 out of 5, with specific, warm comments.",
            evidence_citations=[
                "Jack rated Ivy 5/5: 'Ivy keeps the team organized and unblocks people fast.'",
                "Kim rated Ivy 5/5: 'Ivy is a great communicator and very supportive.'",
            ],
            strengths=["Every peer evaluation is positive and specific, with no signs of friction"],
            areas_for_improvement=["No constructive critique appears anywhere in peer feedback"],
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
    overall_score=7,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=9,
            justification="Liam's 4 commits are large but well-scoped, each covering one part of the payments feature.",
            evidence_citations=[
                "Liam's 'Build payment processing service' commit is a substantial +280/-15 change.",
                "Liam's 'Implement refund flow' commit is a focused +160/-10 change.",
            ],
            strengths=["Each commit maps cleanly to one payments sub-feature"],
            areas_for_improvement=["Commits this large would benefit from incremental PR review"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=6,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                "No Jira ticket or commit in this sprint references writing or updating tests.",
            ],
            strengths=["The refund flow, a financially sensitive feature, still shipped without visible defects reported"],
            areas_for_improvement=["No dedicated testing ticket or commit exists for the payments module"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=6,
            justification="No dedicated documentation ticket exists, though Liam's commit messages clearly describe scope.",
            evidence_citations=[
                "Jira tickets PAY-1 through PAY-4 have clear, specific summaries.",
                "None of the 6 commits touch a docs/ or README file, despite introducing 4 new payments modules (service.py, webhooks.py, refunds.py, audit_log.py).",
            ],
            strengths=["Ticket and commit descriptions are specific and traceable"],
            areas_for_improvement=["No README or API documentation was produced for the new payments service"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=8,
            justification="All 4 planned Jira tickets are marked Done, totaling 21 story points.",
            evidence_citations=[
                "Jira tickets PAY-1 through PAY-4 are all marked Done.",
                "21 of 21 planned story points were delivered.",
            ],
            strengths=["100% ticket completion for the sprint"],
            areas_for_improvement=["All delivery risk was concentrated in a single contributor"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=2,
            justification="One member did all planned work while the other two made only token commits; peer evaluations confirm this directly.",
            evidence_citations=[
                "Maya rated Liam 5/5: 'Liam carried the entire payments module practically by himself.'",
                "Liam rated Maya and Noah 2/5 each, citing a one-line config fix and a .gitignore update as their only contributions.",
            ],
            strengths=["Liam acknowledged the imbalance directly rather than overstating teammates' contributions"],
            areas_for_improvement=["Maya and Noah did not pick up any of the 4 planned tickets", "Workload concentration this severe is a project-risk concern even though delivery succeeded"],
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
    overall_score=3,
    rubric_scores=RubricsScore(
        code_quality=RubricDimensionScore(
            dimension="code_quality",
            score=4,
            justification="All 3 commits are small and one is explicitly unfinished, reflecting a rushed, overloaded effort.",
            evidence_citations=[
                "Uma's second commit message is literally 'WIP, ran out of time'.",
                "Uma's third commit, 'Partial fix for report export bug', is only a +15/-3 partial change.",
            ],
            strengths=["Uma's first commit did establish a working report generation core"],
            areas_for_improvement=["Two of three commits are explicitly incomplete work"],
        ),
        testing=RubricDimensionScore(
            dimension="testing",
            score=3,
            justification="No Jira ticket or commit this sprint references writing or updating tests.",
            evidence_citations=[
                "No Jira ticket or commit in this sprint references writing or updating tests.",
            ],
            strengths=[],
            areas_for_improvement=["No testing was possible given the feature itself was left incomplete"],
        ),
        documentation=RubricDimensionScore(
            dimension="documentation",
            score=3,
            justification="No documentation was produced, consistent with the feature not reaching a stable state.",
            evidence_citations=[
                "No commit or Jira ticket this sprint references documentation.",
            ],
            strengths=[],
            areas_for_improvement=["No documentation exists for the partially-built reporting feature"],
        ),
        requirements=RubricDimensionScore(
            dimension="requirements",
            score=3,
            justification="Only 1 of 4 planned tickets is Done; the rest are In Progress or To Do, all still assigned to a single member.",
            evidence_citations=[
                "Jira ticket REP-1 is marked Done.",
                "Jira tickets REP-2, REP-3, and REP-4 remain In Progress or To Do, all assigned to Uma.",
            ],
            strengths=["The one completed ticket (REP-1) was fully finished"],
            areas_for_improvement=["3 of 4 tickets did not reach Done, and all 4 were carried by one person"],
        ),
        collaboration=RubricDimensionScore(
            dimension="collaboration",
            score=2,
            justification="One member did all the work and it still wasn't enough — peer evaluations confirm both the imbalance and the shortfall.",
            evidence_citations=[
                "Uma rated Victor 1/5: 'Victor did not contribute to any report tickets.'",
                "Wei rated Uma 3/5: 'Uma carried the whole feature alone and it was too much for one person.'",
            ],
            strengths=["Uma's effort was real and acknowledged by teammates, not just self-reported"],
            areas_for_improvement=["Two of three members made zero commits", "The team should not have let all 4 tickets sit with one person"],
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