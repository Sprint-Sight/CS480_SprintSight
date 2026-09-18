# Create rubric score schema for each dimension of the rubric

from typing import Optional
from pydantic import BaseModel, Field
from schemas.rubrics_dimension_score import RubricDimensionScore
# Rubric criteria now lives in prompts/dimension_criteria.py
from prompts.dimension_criteria import DIMENSIONS, DIMENTION_PROMPTS

class RubricsScore(BaseModel):
    code_quality: Optional[RubricDimensionScore] = None
    documentation: Optional[RubricDimensionScore] = None
    testing: Optional[RubricDimensionScore] = None
    requirements: Optional[RubricDimensionScore] = None
    collaboration: Optional[RubricDimensionScore] = None
    cicd: Optional[RubricDimensionScore] = None

    # .scored() replaces iterating a list of dimensions and checking for None, returning only the scored dimensions in the order of DIMENSIONS.
    def scored(self) -> list[RubricDimensionScore]:
        """Dimensions that were successfully evaluated, in DIMENSIONS order."""
        return [score for dim in DIMENSIONS if (score := getattr(self, dim)) is not None]

    # .failed_dimenstions replaces seperately-tracked list field - it can't drift out of sync since it's computed straight from attributed
    @property
    def failed_dimensions(self) -> list[str]:
        return [
            dim for dim in DIMENSIONS
            if (score := getattr(self, dim)) is None or score.evaluation_failed
        ]