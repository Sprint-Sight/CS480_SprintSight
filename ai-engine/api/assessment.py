"""
Declares bundle: ArtifactBundle as a param
FastApi sees that type annotation, reads request body, validates it as ArtifactBundle, injects object auto
Gets back SprintAssessment object from evaluator, which FastAPI serializes to JSON and returns to client
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, status, Query, HTTPException
from pydantic import BaseModel, Field

from schemas.artifact_bundle import ArtifactBundle
from schemas.commit_info import CommitInfo
from schemas.jira import JiraTicket
from schemas.peer_evaluation import PeerEvaluation
from schemas.sprint_assessment import SprintAssessment

from services.evaluator import evaluate_sprint

log = logging.getLogger("sprintsight.router.assessment")

router = APIRouter( # Create router (defines path group)
    prefix="/assess",
    tags=["Sprint Assessment"]
)


class BackendSprintContext(BaseModel):
    course_id: str
    project_id: str
    sprint_id: str
    captured_at: datetime | str


class BackendCollaborationMetrics(BaseModel):
    commit_frequency: float | None = None
    code_churn: int | None = None
    pr_turnaround_hours: float | None = None
    assigned_story_points: int | None = None
    completion_percent: float | None = None


class BackendAssessmentPayload(BaseModel):
    sprint_context: BackendSprintContext
    collaboration_metrics: BackendCollaborationMetrics = Field(default_factory=BackendCollaborationMetrics)
    commits: list[CommitInfo] = Field(default_factory=list)
    jira_tickets: list[JiraTicket] = Field(default_factory=list)
    peer_evaluations: list[PeerEvaluation] = Field(default_factory=list)
    artifact_metrics: dict[str, Any] = Field(default_factory=dict)
    instructor_expectations: str = "No instructor guidance provided."


@router.post("/sprint/data", response_model=SprintAssessment, status_code=status.HTTP_200_OK)
async def assess_backend_data_endpoint(
    payload: BackendAssessmentPayload,
    modelname: str = Query(..., description="Select the model to use for assessment"),
):
    """Accept the backend middleman payload and evaluate it with the configured model."""
    try:
        bundle = ArtifactBundle(
            team_id=payload.sprint_context.project_id,
            sprint_id=payload.sprint_context.sprint_id,
            commits=payload.commits,
            jira_tickets=payload.jira_tickets,
            peer_evaluations=payload.peer_evaluations,
            artifact_metrics=payload.artifact_metrics,
            instructor_expectations=payload.instructor_expectations,
        )
        assessment = await evaluate_sprint(bundle, modelname)
        return assessment
    except Exception as exc:
        log.exception("AI-engine backend assessment failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc