from fastapi import HTTPException, status

from app.core.security import verify_password
from app.repositories.in_memory import users_repo
from app.repositories.interfaces import UserRecord


def authenticate_user(email: str, password: str) -> UserRecord:
    user = users_repo.get_by_email(email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return user


def get_user_by_id(user_id: str) -> UserRecord:
    user = users_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user
