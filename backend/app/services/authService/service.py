import secrets
from uuid import uuid4

from fastapi import HTTPException, status
from psycopg.errors import UniqueViolation

from app.core.security import hash_password, verify_password
from app.repositories.interfaces import UserRecord, UserRepository
from app.schemas.auth import Role


def generate_placeholder_password() -> str:
    return secrets.token_urlsafe(24)


def authenticate_user(repository: UserRepository, email: str, password: str) -> UserRecord:
    user = repository.get_by_email(email)
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return user


def user_response(user: UserRecord):
    from app.schemas.auth import UserResponse

    return UserResponse(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role,
        is_active=user.is_active, must_change_password=user.must_change_password,
        student_number=user.student_number,
    )


def get_user_by_id(repository: UserRepository, user_id: str) -> UserRecord:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user


def create_user(
    repository: UserRepository,
    email: str,
    full_name: str,
    role: Role,
    password: str,
    student_number: int | None = None,
) -> UserRecord:
    if repository.get_by_email(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")
    if student_number is not None and repository.get_by_student_number(student_number):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student number is already registered.")

    try:
        return repository.create_user(UserRecord(
            id=str(uuid4()), email=email.lower(), full_name=full_name, role=role,
            hashed_password=hash_password(password), must_change_password=True,
            student_number=student_number,
        ))
    except (UniqueViolation, ValueError) as exc:
        existing = repository.get_by_email(email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.") from exc
        if student_number is not None and repository.get_by_student_number(student_number):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student number is already registered.",
            ) from exc
        raise
def change_password(repository: UserRepository, user: UserRecord, current_password: str, new_password: str) -> UserRecord:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    updated = repository.update_password(user.id, hash_password(new_password), False)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated


def reset_password(
    repository: UserRepository,
    user_id: str,
    password: str,
    must_change_password: bool = True,
) -> UserRecord:
    updated = repository.update_password(user_id, hash_password(password), must_change_password)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated
