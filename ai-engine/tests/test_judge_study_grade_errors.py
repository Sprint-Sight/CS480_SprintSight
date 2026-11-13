"""The judge study's grade-error columns are filled, with the definitions they have always had.

The grade scorer renamed its per-dimension MAE to `grade_mae_scored_only` and stopped emitting the
overall error (93156b5), while the judge study kept reading `grade_mae_per_dimension` and
`grade_abs_error_overall`, so both columns were silently empty on every run.
"""

from typing import cast

import pytest
from evaluation.judges.grade_accuracy import numeric_grade_accuracy
from evaluation.offline.judge_study.deterministic import numeric_grade_errors
from evaluation.offline.judge_study.records import synthetic_records
from mlflow.entities import Feedback
from prompts.dimension_criteria import DIMENSIONS


@pytest.mark.parametrize("record", synthetic_records(), ids=lambda r: f"{r.model}-{r.example_id}")
def test_grade_error_columns_are_filled_for_every_candidate_with_gold(record) -> None:
    errors = numeric_grade_errors(record.candidate, record.gold)

    overall = float(record.candidate.overall_score) - float(record.gold.overall_score)
    assert errors["grade_signed_error_overall"] == overall
    assert errors["grade_abs_error_overall"] == abs(overall)
    assert errors["grade_mae_per_dimension"] is not None
    assert errors["grade_mae_per_dimension"] == errors["grade_mae_scored_only"]


def test_per_dimension_mae_matches_the_scorers_definition() -> None:
    record = next(r for r in synthetic_records() if r.model == "synthetic-degraded")
    candidate, gold = record.candidate, record.gold
    assert candidate is not None and gold is not None

    diffs = [
        abs(getattr(candidate.rubric_scores, d).score - getattr(gold.rubric_scores, d).score)
        for d in DIMENSIONS
    ]
    errors = numeric_grade_errors(candidate, gold)

    assert errors["grade_mae_per_dimension"] == round(sum(diffs) / len(diffs), 4)
    feedback = cast(list[Feedback], numeric_grade_accuracy(
        outputs=candidate.model_dump(mode="json"), expectations={"gold": gold.model_dump(mode="json")}
    ))
    scorer_mae = next(f.value for f in feedback if f.name == "grade_mae_scored_only")
    assert errors["grade_mae_per_dimension"] == scorer_mae


def test_a_faithful_copy_of_gold_has_zero_error() -> None:
    record = next(r for r in synthetic_records() if r.model == "synthetic-faithful")

    errors = numeric_grade_errors(record.candidate, record.gold)

    assert errors["grade_mae_per_dimension"] == 0.0
    assert errors["grade_abs_error_overall"] == 0.0
