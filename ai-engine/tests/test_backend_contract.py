"""The backend's tests parse backend/tests/fixtures/engine_sprint_assessment.json; this test checks
that the engine's own schema still accepts (and would produce) the same document. If either side
changes the response shape or the dimension order, one of the two tests fails."""

import json
from pathlib import Path

from prompts.dimension_criteria import DIMENSIONS
from schemas.sprint_assessment import SprintAssessment

GOLDEN = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "engine_sprint_assessment.json"


def test_the_backend_golden_response_is_a_valid_engine_response() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    order = data.pop("contract_dimension_order")

    parsed = SprintAssessment.model_validate(data)

    assert order == list(DIMENSIONS), "Update trace_summary.AI_ENGINE_DIMENSION_ORDER in the backend too."
    assert parsed.model_dump(mode="json") == data  # nothing dropped, nothing invented
