from enum import Enum

from pydantic import BaseModel, EmailStr


class Role(str, Enum):
    INSTRUCTOR = "instructor"
    STUDENT = "student"
    ADMIN = "admin"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
