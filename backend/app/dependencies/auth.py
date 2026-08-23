from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import TokenPayloadError, decode_access_token
from app.repositories.interfaces import UserRepository
from app.schemas.auth import Role
from app.services.authService.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.user_repository


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
):
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

    return get_user_by_id(repository, payload["sub"])


def require_faculty(current_user=Depends(get_current_user)):
    if current_user.role != Role.INSTRUCTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty role required.")
    return current_user


def require_student_or_faculty(current_user=Depends(get_current_user)):
    if current_user.role not in (Role.INSTRUCTOR, Role.STUDENT, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return current_user
