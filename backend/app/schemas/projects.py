from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.auth import Role, UserResponse


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)


class CourseResponse(BaseModel):
    id: UUID
    code: str
    name: str
    created_at: datetime


class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    github_repo_url: str | None = Field(default=None, max_length=255)
    member_ids: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    github_repo_url: str | None = Field(default=None, max_length=255)


class ProjectResponse(BaseModel):
    id: UUID
    project_name: str
    description: str | None
    course_code: str
    github_repo_url: str | None
    created_by: str
    created_at: datetime
    members: list[UserResponse]


class InstructorStudentCreate(BaseModel):
    email: str
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class CourseInstructorResponse(BaseModel):
    course_id: UUID
    user_id: str
    role: Role