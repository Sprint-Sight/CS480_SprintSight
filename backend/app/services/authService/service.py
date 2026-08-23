from fastapi import HTTPException, status

from app.core.security import verify_password
from app.repositories.interfaces import UserRecord, UserRepository


def authenticate_user(repository: UserRepository, email: str, password: str) -> UserRecord:
    user = repository.get_by_email(email)
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return user


def get_user_by_id(repository: UserRepository, user_id: str) -> UserRecord:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return user
