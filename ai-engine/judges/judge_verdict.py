"""
schemas/judge_verdict.py

Structured output contract for the LLM-as-a-Judge. One judge call evaluates an
ENTIRE candidate SprintAssessment against the gold SprintAssessment and the raw
ArtifactBundle in a single shot -- not one call per dimension. With 5 candidate
models x 5 fixtures x 5 dimensions, a per-dimension judge would need 125 local
LLM calls per benchmark run on top of the 125 grading calls already made by
evaluate_sprint(). One consolidated judge call per (model, fixture) keeps this
runnable on a laptop-class Ollama instance: 25 judge calls per benchmark run.

Two things this judge is asked to do, both of which need a language model
(neither is a deterministic/code check):

  1. Groundedness -- is each evidence_citations string actually supported by
     the raw commits / jira_tickets in the ArtifactBundle,
     or does it assert something the bundle doesn't contain? Citations here
     are free-text paraphrases (e.g. "Jira ticket AUTH-2 'Auth Tests' is
     marked Done, assigned to Bob."), not machine-checkable file:line spans,
     so this can't be done with a regex/string-match scorer -- it needs
     semantic judgment.

  2. Recommendation actionability -- do key_recommendations name a concrete,
     assignable next step (not generic filler like "improve communication"),
     and do they target the team's actual weakest dimension(s) rather than a
     dimension that was already strong?

Numerical grade accuracy and discriminative (cross-fixture) ordering are
deliberately NOT judged by the LLM -- see llmops/benchmark_scorers.py and
research/run_llm_judge_benchmark.py, which compute both in plain Python
against benchmark.py's gold scores. Asking a judge model to "check how close
two integers are" or "check per-fixture rank order" adds LLM cost, latency,
and its own error source for something arithmetic can do exactly.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DIMENSIONS = ["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]

GroundingLabel = Literal["grounded", "partially_grounded", "hallucinated"]

class CitationVerdict(BaseModel):
    citation: str = Field(description="The evidence_citations string being judged, verbatim.")
    grounded: GroundingLabel
    reasoning: str = Field(
        min_length=10,
        description="One sentence: what in the bundle supports/contradicts this citation, or what's missing.",
    )

    @field_validator("citation", mode="before")
    @classmethod
    def coerce_citation_string(cls, value):
        # Same defensive coercion as RubricDimensionScore.evidence_citations --
        # local models occasionally echo the citation back wrapped in a dict.
        if isinstance(value, dict):
            text = value.get("text") or value.get("citation") or value.get("value")
            return text if isinstance(text, str) else str(value)
        return value


class DimensionGroundingVerdict(BaseModel):
    dimension: Literal["code_quality", "testing", "documentation", "requirements", "collaboration", "cicd"]
    citation_verdicts: list[CitationVerdict]

    @property
    def hallucinated_count(self) -> int: # Counts how many citations were judged as hallucinated for this dimension
        return sum(1 for c in self.citation_verdicts if c.grounded == "hallucinated")

    @property
    def total_count(self) -> int:
        return len(self.citation_verdicts)


class RecommendationVerdict(BaseModel):
    recommendation: str = Field(description="The key_recommendations string being judged, verbatim.")
    targets_true_bottleneck: bool = Field(
        description="True if this recommendation addresses one of the team's actual lowest-scoring "
        "dimensions per the gold assessment, not a dimension that was already strong."
    )
    is_actionable: bool = Field(
        description="True if this names a concrete, assignable next step. False for generic filler "
        "like 'communicate better' or 'try harder' with no specific action."
    )
    reasoning: str = Field(min_length=10)


class JudgeVerdict(BaseModel):
    """Top-level structured response_model passed to instructor for a single
    (candidate_model, fixture) judge call."""

    team_id: str
    sprint_id: str
    candidate_model: str
    dimension_grounding: list[DimensionGroundingVerdict]
    recommendation_verdicts: list[RecommendationVerdict]
    judge_notes: str = Field(
        min_length=10,
        description="1-3 sentence overall summary of judgment quality, independent of the structured fields above.",
    )

    @field_validator("dimension_grounding")
    @classmethod
    def must_cover_all_scored_dimensions(cls, value):
        seen = {v.dimension for v in value}
        if len(seen) != len(value):
            raise ValueError("dimension_grounding has duplicate dimension entries")
        return value

    @property
    def total_citations(self) -> int:
        return sum(d.total_count for d in self.dimension_grounding)

    @property
    def hallucinated_citations(self) -> int:
        return sum(d.hallucinated_count for d in self.dimension_grounding)

    @property
    def hallucination_rate(self) -> float | None:
        if self.total_citations == 0:
            return None
        return round(self.hallucinated_citations / self.total_citations, 4)

    @property
    def actionable_and_targeted_rate(self) -> float | None:
        if not self.recommendation_verdicts:
            return None
        good = sum(
            1 for r in self.recommendation_verdicts
            if r.is_actionable and r.targets_true_bottleneck
        )
        return round(good / len(self.recommendation_verdicts), 4)