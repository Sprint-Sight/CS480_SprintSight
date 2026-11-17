"""What the backend assumes about the engine's response, checked against a golden document the
engine's own tests (ai-engine/tests/test_backend_contract.py) also validate."""

import json
from pathlib import Path

from app.services.assessmentService.service import convert_ai_result_to_assessment_report
from app.services.insightsService.trace_summary import AI_ENGINE_DIMENSION_ORDER, collect_claims

GOLDEN = Path(__file__).parent / "fixtures" / "engine_sprint_assessment.json"
PAYLOAD = {"course_id": "c", "project_id": "p", "sprint_id": "sprint-1", "model_name": "m"}


def _engine_response() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_dimension_order_matches_the_engine() -> None:
    assert list(AI_ENGINE_DIMENSION_ORDER) == _engine_response()["contract_dimension_order"]


def test_engine_response_converts_to_a_report_without_the_failed_dimension() -> None:
    report = convert_ai_result_to_assessment_report(PAYLOAD, _engine_response())

    assert report.trace_id == "tr-golden"
    assert report.failed_dimensions == ["cicd"]
    assert report.evaluation_failed is True
    assert set(report.rubric_scores) == set(AI_ENGINE_DIMENSION_ORDER)
    assert report.rubric_scores["cicd"].evaluation_failed is True
    assert report.rubric_scores["cicd"].failure_class == "timeout"
    # team score averages only the five assessed dimensions (7 each) and renormalises
    assert report.team_score.score == 70.0
    assert report.ai_rubric_scores_original == {
        name: 7.0 for name in AI_ENGINE_DIMENSION_ORDER if name != "cicd"
    }
    assert report.rubric_scores["code_quality"].evidence_details[0].identifier == "src/app.py:L10-L24@abc1234"


def test_judge_claim_numbering_follows_the_engines_order_and_skips_failed_dimensions() -> None:
    outputs = {"rubric_scores": _engine_response()["rubric_scores"]}

    claims = collect_claims(outputs)

    # 5 assessed dimensions x 2 citations; the failed one (cicd) is skipped, as in the judge
    assert list(claims) == [f"C{n}" for n in range(1, 11)]
    assert claims["C1"].startswith("src/app.py:L10-L24@abc1234 | code_quality")
    assert claims["C3"].startswith("src/app.py:L10-L24@abc1234 | testing")
