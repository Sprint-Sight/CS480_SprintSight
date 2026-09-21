from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenPayloadError, decode_access_token
from app.repositories.in_memory import InMemoryDocumentRepository, jira_ingestion_repo, manual_text_repo, metrics_repo, rubric_weights_repo
from app.repositories.interfaces import AssessmentRepository, DocumentRepository, JiraIngestionRunRepository, ManualTextRepository, MetricsRepository, ProjectRepository, RubricWeightsRepository, UserRepository
from app.schemas.auth import Role
from app.services.authService.service import get_user_by_id

oauth2_scheme = HTTPBearer()


def get_user_repository(request: Request) -> UserRepository:
    return request.app.state.user_repository


def get_project_repository(request: Request) -> ProjectRepository:
    return request.app.state.project_repository


def get_metrics_repository(request: Request) -> MetricsRepository:
    return getattr(request.app.state, "metrics_repository", metrics_repo)


def get_document_repository(request: Request) -> DocumentRepository:
    return getattr(request.app.state, "document_repository", InMemoryDocumentRepository())


def get_jira_ingestion_repository(request: Request) -> JiraIngestionRunRepository:
    return getattr(request.app.state, "jira_ingestion_repository", jira_ingestion_repo)


def get_manual_text_repository(request: Request) -> ManualTextRepository:
    return getattr(request.app.state, "manual_text_repository", manual_text_repo)


def get_assessment_repository(request: Request) -> AssessmentRepository:
    return getattr(request.app.state, "assessment_repository", None)


def get_rubric_weights_repository(request: Request) -> RubricWeightsRepository:
    return getattr(request.app.state, "rubric_weights_repository", rubric_weights_repo)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_scheme)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        token_id = str(UUID(payload["jti"]))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.") from exc
    if repository.is_access_token_revoked(token_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been revoked.")

    user = get_user_by_id(repository, payload["sub"])
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive.")
    if payload["token_version"] != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been invalidated.")
    return user


def require_password_changed(current_user=Depends(get_current_user)):
    if current_user.must_change_password:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password change required.")
    return current_user


def require_faculty(current_user=Depends(require_password_changed)):
    if current_user.role not in (Role.INSTRUCTOR, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Faculty role required.")
    return current_user


def require_instructor(current_user=Depends(require_password_changed)):
    if current_user.role != Role.INSTRUCTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required.")
    return current_user


def require_student_or_faculty(current_user=Depends(require_password_changed)):
    if current_user.role not in (Role.INSTRUCTOR, Role.STUDENT, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
    return current_user


def require_admin(current_user=Depends(require_password_changed)):
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")
    return current_user
