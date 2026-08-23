from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import create_access_token, decode_access_token
from app.dependencies.auth import get_user_repository, get_current_user, oauth2_scheme, require_student_or_faculty
from app.repositories.interfaces import UserRecord, UserRepository
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserResponse
from app.services.authService.service import authenticate_user, change_password, user_response

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
) -> UserResponse:
    return user_response(change_password(repository, current_user, payload.current_password, payload.new_password))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    credentials: Annotated[object, Depends(oauth2_scheme)],
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> None:
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        token_id = str(UUID(payload["jti"]))
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc

    repository.revoke_access_token(token_id, current_user.id, expires_at)


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[object, Depends(require_student_or_faculty)]) -> UserResponse:
    return user_response(current_user)
