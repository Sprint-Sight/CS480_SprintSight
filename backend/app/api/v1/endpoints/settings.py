from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.config import get_settings
from app.core.credential_crypto import encrypt_secret
from app.dependencies.auth import (
    get_action_audit_repository,
    get_instructor_jira_credentials_repository,
    require_faculty,
)
from app.repositories.interfaces import (
    ActionAuditRepository,
    InstructorJiraCredentialsRecord,
    InstructorJiraCredentialsRepository,
)
from app.services.auditLogService.service import append_action_audit

router = APIRouter(prefix="/settings", tags=["settings"])


class JiraCredentialsResponse(BaseModel):
    jira_email: str
    jira_token_configured: bool
    is_saved: bool


class JiraCredentialsPayload(BaseModel):
    jira_email: EmailStr | None = None
    jira_api_token: str | None = None


def _response(
    record: InstructorJiraCredentialsRecord | None,
) -> JiraCredentialsResponse:
    settings = get_settings()
    return JiraCredentialsResponse(
        jira_email=(record.jira_email if record and record.jira_email else settings.jira_email),
        jira_token_configured=bool(
            (record and record.jira_api_token_encrypted) or settings.jira_api_token
        ),
        is_saved=record is not None,
    )


@router.get("/jira-credentials", response_model=JiraCredentialsResponse)
def get_jira_credentials(
    faculty_user: Annotated[object, Depends(require_faculty)],
    repository: Annotated[
        InstructorJiraCredentialsRepository,
        Depends(get_instructor_jira_credentials_repository),
    ],
) -> JiraCredentialsResponse:
    """Return the instructor's Jira email and whether a token is configured.

    The token itself is never returned to the browser.
    """
    return _response(repository.get_credentials(faculty_user.id))


@router.put("/jira-credentials", response_model=JiraCredentialsResponse)
def put_jira_credentials(
    payload: JiraCredentialsPayload,
    faculty_user: Annotated[object, Depends(require_faculty)],
    repository: Annotated[
        InstructorJiraCredentialsRepository,
        Depends(get_instructor_jira_credentials_repository),
    ],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> JiraCredentialsResponse:
    existing = repository.get_credentials(faculty_user.id)
    fields_set = payload.model_fields_set
    jira_email = (
        str(payload.jira_email)
        if "jira_email" in fields_set and payload.jira_email
        else None
        if "jira_email" in fields_set
        else existing.jira_email if existing else None
    )

    if "jira_api_token" in fields_set:
        token = payload.jira_api_token
        encrypted_token = encrypt_secret(token) if token else None
    else:
        encrypted_token = existing.jira_api_token_encrypted if existing else None

    if encrypted_token and not jira_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A Jira email is required when a Jira API token is configured.",
        )

    record = repository.set_credentials(
        faculty_user.id,
        jira_email,
        encrypted_token,
    )
    append_action_audit(
        action_audits,
        actor_id=faculty_user.id,
        actor_role=faculty_user.role.value,
        action="update_jira_credentials",
        target_type="user",
        target_id=faculty_user.id,
        details={"jira_token_configured": bool(record.jira_api_token_encrypted)},
    )
    return _response(record)
