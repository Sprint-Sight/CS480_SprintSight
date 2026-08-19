from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_faculty
from app.schemas.assessment import ManualTextPayload
from app.services.manualTextService.service import get_manual_text, upsert_manual_text

router = APIRouter(prefix="/manual-text", tags=["manual-text"])


@router.put("")
def put_manual_text(
    payload: ManualTextPayload,
    faculty_user: Annotated[object, Depends(require_faculty)],
) -> dict[str, str]:
    upsert_manual_text(payload, updated_by=faculty_user.id)
    return {"status": "saved"}


@router.get("")
def read_manual_text(
    course_id: str,
    project_id: str,
    sprint_id: str,
    faculty_user: Annotated[object, Depends(require_faculty)],
) -> dict[str, str | None]:
    _ = faculty_user
    return {"expectations_text": get_manual_text(course_id, project_id, sprint_id)}
