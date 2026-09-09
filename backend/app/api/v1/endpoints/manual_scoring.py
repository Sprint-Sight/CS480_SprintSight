from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import (
    get_project_repository,
    require_instructor,
    require_password_changed,
)
from app.dependencies.manual_scoring import get_manual_override_repository
from app.repositories.interfaces import ProjectRepository, UserRecord
from app.repositories.manual_override import ManualOverrideRepository
from app.schemas.manual_scoring import ManualOverrideCreate, ManualOverrideResponse
from app.services.manualScoringService.service import ManualScoringService

router = APIRouter(prefix="/manual-scoring", tags=["manual-scoring"])


def _response(record) -> ManualOverrideResponse:
    return ManualOverrideResponse.model_validate(record.__dict__)


@router.post("/overrides", response_model=ManualOverrideResponse, status_code=status.HTTP_200_OK)
def create_or_update_override(
    payload: ManualOverrideCreate,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    overrides: Annotated[ManualOverrideRepository, Depends(get_manual_override_repository)],
) -> ManualOverrideResponse:
    record = ManualScoringService(overrides, projects).create_or_update(payload, current_user)
    return _response(record)


@router.get("/overrides", response_model=list[ManualOverrideResponse])
def list_overrides(
    current_user: Annotated[UserRecord, Depends(require_password_changed)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    overrides: Annotated[ManualOverrideRepository, Depends(get_manual_override_repository)],
    project_id: Annotated[str, Query(min_length=1, max_length=100)],
    course_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sprint_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> list[ManualOverrideResponse]:
    records = ManualScoringService(overrides, projects).list_overrides(
        course_id=course_id, project_id=project_id, sprint_id=sprint_id, user=current_user
    )
    return [_response(record) for record in records]
