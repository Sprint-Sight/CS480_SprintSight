from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.credential_crypto import normalize_jira_domain
from app.schemas.auth import Role, UserResponse


# ---------------------------------------------------------------------------
# Shared field-level helpers (reused by both Create and Update)
# ---------------------------------------------------------------------------

def _validate_github_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().rstrip("/")
    if not value.startswith("https://"):
        raise ValueError("Repository URL must use HTTPS (e.g. https://github.com/org/repo).")
    allowed_hosts = ("github.com/", "gitlab.com/")
    if not any(f"/{host}" in value or value[8:].startswith(host) for host in allowed_hosts):
        raise ValueError("Repository URL must be a GitHub or GitLab URL.")
    path = value[8:].split("/", 1)
    if len(path) < 2 or not path[1]:
        raise ValueError("Repository URL must include an organisation and repository name.")
    return value


def _validate_local_path(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("Local repository path cannot be blank.")
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise ValueError(
            "Local repository path must be relative to LOCAL_REPOSITORY_ROOT, "
            "not an absolute path (e.g. use 'team-alpha/repo', not '/app/repo/...')."
        )
    if any(segment == ".." for segment in value.replace("\\", "/").split("/")):
        raise ValueError("Local repository path must not contain '..' (path traversal is not allowed).")
    return value


# ---------------------------------------------------------------------------
# Course schemas
# ---------------------------------------------------------------------------

class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=150)
    section: str = Field(min_length=1, max_length=20)
    year: int = Field(ge=2000, le=2100)
    term: str = Field(min_length=1, max_length=20)


class CourseResponse(BaseModel):
    id: UUID
    code: str
    name: str
    section: str
    year: int
    term: str
    created_by: str
    created_at: datetime


class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    section: str | None = Field(default=None, min_length=1, max_length=20)
    year: int | None = Field(default=None, ge=2000, le=2100)
    term: str | None = Field(default=None, min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# Project — Create
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    project_name: str = Field(min_length=1, max_length=150)
    team_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    github_repo_url: str | None = Field(default=None, min_length=1, max_length=255)
    local_repo_path: str | None = Field(default=None, max_length=255)
    jira_email: EmailStr
    jira_domain: str | None = Field(default=None, max_length=255)
    jira_project_key: str | None = Field(default=None, max_length=50)
    jira_api_token: str | None = Field(default=None, max_length=512)
    member_ids: list[str] = Field(default_factory=list)

    @field_validator("member_ids")
    @classmethod
    def validate_unique_members(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate student IDs found in member_ids list.")
        return value

    @field_validator("team_name")
    @classmethod
    def validate_team_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Team name cannot be blank.")
        return value

    @field_validator("github_repo_url")
    @classmethod
    def validate_github_repo_url(cls, value: str | None) -> str | None:
        return _validate_github_url(value)

    @field_validator("local_repo_path")
    @classmethod
    def validate_local_repo_path(cls, value: str | None) -> str | None:
        return _validate_local_path(value)

    @field_validator("jira_domain")
    @classmethod
    def validate_jira_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        domain = normalize_jira_domain(value)
        if not domain:
            raise ValueError("Jira domain cannot be blank.")
        return domain

    @field_validator("jira_project_key", "jira_api_token")
    @classmethod
    def validate_non_empty_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Field cannot be blank.")
        return value


# ---------------------------------------------------------------------------
# Project — Update
# ---------------------------------------------------------------------------

class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=150)
    team_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

    github_repo_url: str | None = Field(default=None, max_length=255)
    local_repo_path: str | None = Field(default=None, max_length=255)

    jira_email: EmailStr | None = None
    jira_domain: str | None = Field(default=None, max_length=255)
    jira_project_key: str | None = Field(default=None, max_length=50)
    jira_api_token: str | None = Field(default=None, max_length=512)

    @field_validator("team_name")
    @classmethod
    def validate_team_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Team name cannot be blank.")
        return value

    @field_validator("github_repo_url")
    @classmethod
    def validate_github_repo_url(cls, value: str | None) -> str | None:
        return _validate_github_url(value)

    @field_validator("local_repo_path")
    @classmethod
    def validate_local_repo_path(cls, value: str | None) -> str | None:
        return _validate_local_path(value)

    @field_validator("jira_domain")
    @classmethod
    def validate_jira_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        domain = normalize_jira_domain(value)
        if not domain:
            raise ValueError("Jira domain cannot be blank.")
        return domain

    @field_validator("jira_project_key")
    @classmethod
    def validate_jira_project_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Jira project key cannot be blank.")
        return value


# ---------------------------------------------------------------------------
# Project — Response
# ---------------------------------------------------------------------------

class ProjectResponse(BaseModel):
    id: UUID
    project_name: str
    team_name: str
    description: str | None
    course_code: str
    github_repo_url: str | None
    local_repo_path: str | None
    jira_email: str | None
    jira_domain: str | None
    jira_project_key: str | None
    jira_token_configured: bool
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