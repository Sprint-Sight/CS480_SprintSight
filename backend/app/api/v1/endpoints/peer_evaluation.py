"""Peer evaluation endpoints.

Students evaluate their project group members (1-5 rating + remarks + reason).
Students can only see their own submissions. Instructors see all evaluations
in their course and control the evaluation window (open/close + expiry).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies.auth import (
    get_action_audit_repository,
    get_peer_evaluation_repository,
    get_project_repository,
    get_user_repository,
    require_faculty,
    require_student_or_faculty,
)
from app.repositories.interfaces import (
    ActionAuditRepository,
    PeerEvaluationRepository,
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.auth import Role
from app.schemas.peer_evaluation import (
    CoursePeerEvaluationSummary,
    EvaluationStatusResponse,
    PeerEvaluationConfigCreate,
    PeerEvaluationConfigResponse,
    PeerEvaluationCreate,
    PeerEvaluationResponse,
    PeerEvaluationSummary,
)
from app.services.peerEvaluationService.service import PeerEvaluationService

router = APIRouter(tags=["peer-evaluation"])


def _get_service(
    current_user: UserRecord,
    projects: ProjectRepository,
    users: UserRepository,
    evaluations: PeerEvaluationRepository,
    action_audits: ActionAuditRepository,
) -> PeerEvaluationService:
    return PeerEvaluationService(
        peer_evaluation_repository=evaluations,
        project_repository=projects,
        user_repository=users,
        action_audits=action_audits,
    )


# ------------------------------------------------------------------
# Instructor: configure evaluation window
# ------------------------------------------------------------------

@router.post(
    "/courses/{course_id}/config",
    response_model=PeerEvaluationConfigResponse,
    status_code=status.HTTP_200_OK,
)
def set_peer_evaluation_config(
    course_id: str,
    payload: PeerEvaluationConfigCreate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> PeerEvaluationConfigResponse:
    """Open or close peer evaluation for a course and set an expiry date.

    Only instructors assigned to the course may call this.
    """
    if not projects.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to teach this course.",
        )

    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=None,  # not needed for config
        evaluations=evaluations,
        action_audits=action_audits,
    )
    return service.set_evaluation_config(course_id, payload, current_user.id)


@router.get(
    "/courses/{course_id}/config",
    response_model=PeerEvaluationConfigResponse | None,
)
def get_peer_evaluation_config(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
) -> PeerEvaluationConfigResponse | None:
    """Get the peer evaluation configuration for a course."""
    if not projects.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to teach this course.",
        )

    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=None,
        evaluations=evaluations,
        action_audits=None,
    )
    return service.get_evaluation_config(course_id)


# ------------------------------------------------------------------
# Student: submit evaluation
# ------------------------------------------------------------------

@router.post(
    "/evaluations",
    response_model=PeerEvaluationResponse,
)
def submit_peer_evaluation(
    response: Response,
    payload: PeerEvaluationCreate,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> PeerEvaluationResponse:
    """Submit a peer evaluation of a group member.

    Students can only evaluate members of their own project group.
    Evaluation window must be open and not expired.
    """
    if current_user.role not in (Role.STUDENT,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can submit peer evaluations.",
        )

    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=users,
        evaluations=evaluations,
        action_audits=action_audits,
    )
    result, is_update = service.submit_evaluation(payload, current_user.id)
    response.status_code = status.HTTP_200_OK if is_update else status.HTTP_201_CREATED
    return result


# ------------------------------------------------------------------
# Student: view own evaluations
# ------------------------------------------------------------------

@router.get(
    "/evaluations/mine",
    response_model=list[PeerEvaluationResponse],
)
def list_my_peer_evaluations(
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    project_id: str | None = Query(
        default=None, description="Optional project ID to filter evaluations."
    ),
) -> list[PeerEvaluationResponse]:
    """List evaluations submitted by the current student.

    Students can only see their own evaluations of others.
    """
    if current_user.role not in (Role.STUDENT,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can view their own evaluations.",
        )

    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=users,
        evaluations=evaluations,
        action_audits=None,
    )
    return service.list_my_evaluations(current_user.id, project_id)


# ------------------------------------------------------------------
# Student: check if evaluation is open
# ------------------------------------------------------------------

@router.get(
    "/courses/{course_id}/status",
    response_model=EvaluationStatusResponse,
)
def get_peer_evaluation_status(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(require_student_or_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> EvaluationStatusResponse:
    """Check whether the current student can submit evaluations for a course."""
    if current_user.role not in (Role.STUDENT,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can check evaluation status.",
        )

    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=users,
        evaluations=evaluations,
        action_audits=None,
    )
    status_info = service.get_evaluation_status(course_id, current_user.id)
    return EvaluationStatusResponse(
        can_evaluate=status_info["can_evaluate"],
        is_open=status_info["is_open"],
        expires_at=status_info["expires_at"],
        message=status_info["message"],
    )


# ------------------------------------------------------------------
# Instructor: view all evaluations for a project
# ------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/evaluations",
    response_model=PeerEvaluationSummary,
)
def get_project_peer_evaluations(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> PeerEvaluationSummary:
    """Instructor view: all peer evaluations for a project group."""
    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=users,
        evaluations=evaluations,
        action_audits=action_audits,
    )
    return service.get_project_evaluations(project_id, current_user.id)


# ------------------------------------------------------------------
# Instructor: view all evaluations for a course
# ------------------------------------------------------------------

@router.get(
    "/courses/{course_id}/evaluations",
    response_model=CoursePeerEvaluationSummary,
)
def get_course_peer_evaluations(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    evaluations: Annotated[PeerEvaluationRepository, Depends(get_peer_evaluation_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> CoursePeerEvaluationSummary:
    """Instructor view: all peer evaluations across all projects in a course."""
    service = _get_service(
        current_user=current_user,
        projects=projects,
        users=users,
        evaluations=evaluations,
        action_audits=action_audits,
    )
    return service.get_course_evaluations(course_id, current_user.id)
