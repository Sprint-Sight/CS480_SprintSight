from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenPayloadError, decode_access_token
from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import MetricsRepository, ProjectRepository, UserRepository
from app.schemas.auth import Role
from app.services.authService.service import get_user_by_id

oauth2_scheme = HTTPBearer()


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.user_repository


def get_project_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository


def get_metrics_repository(request: Request) -> MetricsRepository:
    return getattr(request.app.state, "metrics_repository", metrics_repo)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_scheme)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        token_id = str(UUID(payload["jti"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc
    if repository.is_access_token_revoked(token_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked.")

    user = get_user_by_id(repository, payload["sub"])
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive.")
    if payload["token_version"] != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been invalidated.")
    return user


def require_password_changed(current_user=Depends(get_current_user)):
    if current_user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required.")
    return current_user


def require_faculty(current_user=Depends(require_password_changed)):
    if current_user.role not in (Role.INSTRUCTOR, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty role required.")
    return current_user


def require_student_or_faculty(current_user=Depends(require_password_changed)):
    if current_user.role not in (Role.INSTRUCTOR, Role.STUDENT, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return current_user


def require_admin(current_user=Depends(require_password_changed)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    return current_user
