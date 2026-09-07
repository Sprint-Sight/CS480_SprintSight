from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_manual_text_repository, get_project_repository, require_instructor
from app.repositories.interfaces import ManualTextRepository, ProjectRepository, UserRecord
from app.schemas.auth import Role
from app.schemas.assessment import ManualTextPayload
from app.services.manualTextService.service import get_manual_text, upsert_manual_text

router = APIRouter(prefix="/manual-text", tags=["manual-text"])


def _authorized_project(project_id: str, current_user: UserRecord, projects: ProjectRepository):
    project = projects.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.role != Role.INSTRUCTOR or not projects.is_instructor_assigned(project.course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    return project


@router.post("", status_code=status.HTTP_200_OK)
def post_manual_text(
    payload: ManualTextPayload,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    repository: Annotated[ManualTextRepository, Depends(get_manual_text_repository)],
) -> dict[str, str]:
    project = _authorized_project(payload.project_id, current_user, projects)
    if project.course_id != payload.course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to the specified course.")
    upsert_manual_text(repository, payload, updated_by=current_user.id)
    return {"status": "saved"}


@router.get("")
def read_manual_text(
    course_id: str,
    project_id: str,
    sprint_id: str,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    repository: Annotated[ManualTextRepository, Depends(get_manual_text_repository)],
) -> dict[str, str | None]:
    project = _authorized_project(project_id, current_user, projects)
    if project.course_id != course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project does not belong to the specified course.")
    return {"expectations_text": get_manual_text(repository, course_id, project_id, sprint_id)}
