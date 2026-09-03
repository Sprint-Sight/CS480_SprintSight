"""
Declares bundle: ArtifactBundle as a param
FastApi sees that type annotation, reads request body, validates it as ArtifactBundle, injects object auto
Gets back SprintAssessment object from evaluator, which FastAPI serializes to JSON and returns to client
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, status, Query, HTTPException
from pydantic import BaseModel, Field

from schemas.modelname import ModelName
from schemas.teamtype import TeamType
from schemas.artifact_bundle import ArtifactBundle
from schemas.benchmark import SprintAssessment
from schemas.fixtures import high_performing_team, struggling_team, good_collab_low_output_team, lone_contributor_poor_outcome_team, imbalanced_high_output_team

from services.evaluator import evaluate_sprint

log = logging.getLogger("sprintsight.router.assessment")

router = APIRouter( # Create router (defines path group)
    prefix="/assess",
    tags=["Sprint Assessment"]
)


class BackendAssessmentPayload(BaseModel):
    sprint_context: dict = Field(default_factory=dict)
    collaboration_metrics: dict = Field(default_factory=dict)
    commits: list = Field(default_factory=list)
    artifact_metrics: dict = Field(default_factory=dict)
    instructor_expectations: str = ""

## AS OF NOW, WE ARE USING FIXTURE DATA FOR TESTING AND DEMONSTRATION PURPOSES.
team_fixtures = {
    "high_performing_team": high_performing_team,
    "struggling_team": struggling_team,
    "good_collab_low_output_team": good_collab_low_output_team,
    "lone_contributor_poor_outcome_team": lone_contributor_poor_outcome_team,
    "imbalanced_high_output_team": imbalanced_high_output_team
}

@router.post("/sprint", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_sprint_endpoint(
    key: TeamType = Query(..., description="Select the team type to assess"), 
    modelname: ModelName = Query(..., description="Select the model to use for assessment")
):

    teamtype = team_fixtures.get(key.value) # Get ArtifactBundle given selected team type

    try:
        print("Grading high performing team...")
        assessment = await evaluate_sprint(teamtype, modelname.value, experiment_name="Sprintsight evaluation") # Passes bundle and modelname
        print("\nSUCCESS! Ollama returned structured Pydantic data:")
        return assessment

    except Exception as e:
        print("\nERROR: Ollama failed to return structured Pydantic data:")
        print(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sprint/data", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_backend_data(
    payload: BackendAssessmentPayload,
    modelname: ModelName = Query(ModelName.SPRINTSIGHT_LLAMA),
):
    sprint_context = payload.sprint_context
    project_id = sprint_context.get("project_id")
    sprint_id = sprint_context.get("sprint_id")
    if not project_id or not sprint_id:
        raise HTTPException(status_code=422, detail="sprint_context requires project_id and sprint_id")

    bundle = ArtifactBundle(
        team_id=project_id,
        sprint_id=sprint_id,
        commits=payload.commits,
        sprint_context=sprint_context,
        collaboration_metrics=payload.collaboration_metrics,
        artifact_metrics=payload.artifact_metrics,
        instructor_expectations=payload.instructor_expectations,
    )
    try:
        return await evaluate_sprint(bundle, modelname.value)
    except Exception as exc:
        log.exception("AI assessment failed for project %s, sprint %s", project_id, sprint_id)
        raise HTTPException(status_code=502, detail="AI assessment failed") from exc