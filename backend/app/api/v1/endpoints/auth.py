from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import create_access_token
from app.dependencies.auth import require_student_or_faculty
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.authService.service import authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate_user(payload.email, payload.password)
    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[object, Depends(require_student_or_faculty)]) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
    )
