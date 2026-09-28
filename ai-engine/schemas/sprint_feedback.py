from pydantic import BaseModel


class SprintFeedback(BaseModel):
    """General feedback for the whole sprint, separate from rubric scores."""

    strengths: list[str]
    weaknesses: list[str]
    recommendations: list[str]