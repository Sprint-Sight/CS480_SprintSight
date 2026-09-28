# Create rubric score schema for each dimension of the rubric


from pydantic import BaseModel

# Rubric criteria now lives in prompts/dimension_criteria.py
from prompts.dimension_criteria import DIMENSIONS
from schemas.rubrics_dimension_score import RubricDimensionScore


class RubricsScore(BaseModel):
    code_quality: RubricDimensionScore | None = None
    documentation: RubricDimensionScore | None = None
    testing: RubricDimensionScore | None = None
    requirements: RubricDimensionScore | None = None
    collaboration: RubricDimensionScore | None = None
    cicd: RubricDimensionScore | None = None

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