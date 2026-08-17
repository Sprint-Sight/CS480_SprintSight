"""
Declares bundle: ArtifactBundle as a param
FastApi sees that type annotation, reads request body, validates it as ArtifactBundle, injects object auto
Gets back SprintAssessment object from evaluator, which FastAPI serializes to JSON and returns to client
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, status, Query, HTTPException

from schemas.modelname import ModelName
from schemas.teamtype import TeamType
from schemas.assessment import SprintAssessment
from schemas.fixtures import high_performing_team, imbalanced_team, struggling_team

from services.evaluator import evaluate_sprint

log = logging.getLogger("sprintsight.router.assessment")

router = APIRouter( # Create router (defines path group)
    prefix="/assess",
    tags=["Sprint Assessment"]
)

## AS OF NOW, WE ARE USING FIXTURE DATA FOR TESTING AND DEMONSTRATION PURPOSES.
team_fixtures = {
    "high_performing_team": high_performing_team,
    "imbalanced_team": imbalanced_team,
    "struggling_team": struggling_team,
}

@router.post("/sprint", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_sprint_endpoint(
    key: TeamType = Query(..., description="Select the team type to assess"), 
    modelname: ModelName = Query(..., description="Select the model to use for assessment")
):

    teamtype = team_fixtures.get(key.value) # Get ArtifactBundle given selected team type

    try:
        print("Grading high performing team...")
        assessment = await evaluate_sprint(teamtype, modelname.value) # Passes bundle and modelname
        print("\nSUCCESS! Ollama returned structured Pydantic data:")
        return assessment

    except Exception as e:
        print("\nERROR: Ollama failed to return structured Pydantic data:")
        print(e)
        raise HTTPException(status_code=500, detail=str(e))