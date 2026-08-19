from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import TokenPayloadError, decode_access_token
from app.schemas.auth import Role
from app.services.authService.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        payload = decode_access_token(token)
    except TokenPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return get_user_by_id(payload["sub"])


def require_faculty(current_user=Depends(get_current_user)):
    if current_user.role != Role.FACULTY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty role required.")
    return current_user


def require_student_or_faculty(current_user=Depends(get_current_user)):
    if current_user.role not in (Role.FACULTY, Role.STUDENT):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return current_user
