from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_user_repository, require_admin
from app.repositories.interfaces import UserRecord, UserRepository
from app.schemas.auth import AdminPasswordReset, AdminUserCreate, AdminUserUpdate, Role, UserResponse
from app.services.authService.service import create_user, reset_password, user_response

router = APIRouter(prefix="/users", tags=["users"])


def _active_admin_count(repository: UserRepository) -> int:
    return sum(user.is_active and user.role == Role.ADMIN for user in repository.list_users())


@router.get("", response_model=list[UserResponse])
def list_users(_: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> list[UserResponse]:
    return [user_response(user) for user in repository.list_users()]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: str, _: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user_response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_managed_user(payload: AdminUserCreate, _: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    return user_response(create_user(repository, payload.email, payload.full_name, payload.role, payload.password))


@router.patch("/{user_id}", response_model=UserResponse)
def update_managed_user(user_id: str, payload: AdminUserUpdate, current_admin: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user_id == current_admin.id and (payload.is_active is False or payload.role not in (None, current_admin.role)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot disable or demote themselves.")
    if user.role == Role.ADMIN and user.is_active and (payload.role not in (None, Role.ADMIN) or payload.is_active is False) and _active_admin_count(repository) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin is required.")
    email = payload.email or user.email
    existing = repository.get_by_email(email)
    if existing and existing.id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")
    updated = repository.update_user(user_id, email, payload.full_name or user.full_name, payload.role or user.role, payload.is_active if payload.is_active is not None else user.is_active)
    return user_response(updated)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_managed_user_password(user_id: str, payload: AdminPasswordReset, _: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    return user_response(reset_password(repository, user_id, payload.password))


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_managed_user(user_id: str, current_admin: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user_id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins cannot disable themselves.")
    if user.role == Role.ADMIN and user.is_active and _active_admin_count(repository) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one active admin is required.")
    updated = repository.update_user(user_id, user.email, user.full_name, user.role, False)
    return user_response(updated)