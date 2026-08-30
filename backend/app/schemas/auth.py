from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class Role(str, Enum):
    INSTRUCTOR = "instructor"
    STUDENT = "student"
    ADMIN = "admin"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    role: Role
    password: str = Field(min_length=8, max_length=128)


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    is_active: bool | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool = True
    must_change_password: bool = False
