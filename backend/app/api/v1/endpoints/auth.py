from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import create_access_token, decode_access_token
from app.dependencies.auth import (
    get_action_audit_repository,
    get_current_user,
    get_user_repository,
    oauth2_scheme,
    require_password_changed,
    require_student_or_faculty,
)
from app.repositories.interfaces import ActionAuditRepository, UserRecord, UserRepository
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserResponse
from app.services.authService.service import authenticate_user, change_password, user_response
from app.services.auditLogService.service import append_action_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> TokenResponse:
    user = authenticate_user(repository, payload.email, payload.password)
    repository.record_login(user.id)
    token = create_access_token(subject=user.id, role=user.role.value, token_version=user.token_version)
    return TokenResponse(access_token=token, must_change_password=user.must_change_password)


@router.post("/change-password", response_model=UserResponse)
def update_password(
    payload: PasswordChangeRequest,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> UserResponse:
    updated = change_password(repository, current_user, payload.current_password, payload.new_password)
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="change_own_password",
        target_type="user",
        target_id=current_user.id,
    )
    return user_response(updated)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[object, Depends(oauth2_scheme)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> None:
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        token_id = str(UUID(payload["jti"]))
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc

    repository.revoke_access_token(token_id, current_user.id, expires_at)
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="logout",
        target_type="user",
        target_id=current_user.id,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[object, Depends(require_password_changed)]) -> UserResponse:
    return user_response(current_user)