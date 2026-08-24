from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_faculty
from app.services.auditLogService.service import list_audit_records

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/overrides")
def get_override_audits(faculty_user: Annotated[object, Depends(require_faculty)]):
    _ = faculty_user
    return list_audit_records()
