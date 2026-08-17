from schemas.sprint_assessment import SprintAssessment
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.member_contribution import MemberContribution

# create a fake final grade to see if Pydantic accepts it
fake_grade = SprintAssessment(
    team_id="Team_Alpha",
    sprint_id="Sprint_1",
    prompt_version="v1.0",
    overall_score=9,
    rubric_scores=[
        RubricDimensionScore(
            dimension="code_quality",
            score=8,
            justification="The code very chapalang",
            evidence_citations=["insert_legit_file_name_here.png"], # insert legit file name here
            strengths=["insert_legit_strength_here"], # insert legit strength here
            areas_for_improvement=["insert_legit_area_for_improvement_here"] # insert legit area
        )
    ],
    member_contributions=[
        MemberContribution(
            student_id="member_1",
            contribution_score=9,
            primary_contributions=["insert_legit_contribution_here"],
            evidence=["insert_legit_evidence_here"]
        ),
        MemberContribution(
            student_id="member_2",
            contribution_score=8,
            primary_contributions=["insert_legit_contribution_here"],
            evidence=["insert_legit_evidence_here"]
        )
    ],
    executive_summary="Overall, so chapalang",
    key_recommendations=["Don't play play hor", "Better buck up ah"]
)

print("SUCCESS! Your schema works.")
print(fake_grade.model_dump_json(indent=2))