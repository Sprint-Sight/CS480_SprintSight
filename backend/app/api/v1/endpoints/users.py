from typing import Annotated

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from app.dependencies.auth import (
    get_action_audit_repository,
    get_notification_service,
    get_project_repository,
    get_user_repository,
    require_admin,
    require_faculty,
)
from app.repositories.interfaces import (
    ActionAuditRepository,
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.auth import (
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserUpdate,
    Role,
    UserCreationResponse,
    UserResponse,
)
from app.services.auditLogService.service import append_action_audit
from app.services.authService.deactivation import deactivate_user_cascade
from app.services.authService.password_setup import send_password_setup_email
from app.services.authService.service import (
    create_user,
    generate_placeholder_password,
    reset_password,
    user_response,
)
from app.services.notificationService.service import (
    NotificationConfigurationError,
    NotificationDeliveryError,
    SMTPNotificationService,
)

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Who can create whom?
#
#   Admin      → POST /users with any role (instructor, student, admin)
#   Instructor → POST /users                    (creates without enrolment)
#                POST /courses/{id}/students    (creates and enrols)
#                POST /courses/{id}/students/{user_id} (enrols an existing student)
#   Student    → cannot create any user
#
# Who can deactivate (soft-delete) whom?
#
#   Admin      → DELETE /users/{id}  for any user EXCEPT themselves and the
#                last remaining active admin.
#   Instructor → cannot deactivate accounts.  They can:
#                  DELETE /courses/{id}/students/{id}  — unenrol from course
#                  DELETE /projects/{id}/members/{id}  — remove from project group
#   Student    → cannot deactivate or remove anyone.
# ---------------------------------------------------------------------------


def _active_admin_count(repository: UserRepository) -> int:
    return sum(1 for u in repository.list_users() if u.is_active and u.role == Role.ADMIN)


@router.get("", response_model=list[UserResponse])
def list_users(
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> list[UserResponse]:
    users = repository.list_users()
    if current_user.role == Role.INSTRUCTOR:
        users = [u for u in users if u.role == Role.STUDENT]
    return [user_response(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if current_user.role == Role.INSTRUCTOR and user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructors can only view student accounts.")
    return user_response(user)


@router.post("", response_model=UserCreationResponse, status_code=status.HTTP_201_CREATED)
def create_managed_user(
    payload: AdminUserCreate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    notification_service: Annotated[SMTPNotificationService, Depends(get_notification_service)],
) -> UserCreationResponse:
    """
    Admin creates any account type (instructor / student / admin).
    Instructors may only create student accounts.
    """
    if current_user.role == Role.INSTRUCTOR and payload.role != Role.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructors can only create student accounts.",
        )
    created = create_user(
        repository,
        str(payload.email),
        payload.full_name,
        payload.role,
        payload.password or generate_placeholder_password(),
        payload.student_number,
    )
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="create_user",
        target_type="user",
        target_id=created.id,
        details={"email": created.email, "role": created.role.value},
    )
    signup_email_sent = send_password_setup_email(created, notification_service)
    return UserCreationResponse(
        **user_response(created).model_dump(),
        account_created=True,
        signup_email_sent=signup_email_sent,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def update_managed_user(
    user_id: str,
    payload: AdminUserUpdate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if current_user.role == Role.INSTRUCTOR:
        if user.role != Role.STUDENT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructors can only manage student accounts.")
        if payload.role not in (None, Role.STUDENT):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructors cannot change a user's role.")

    # Prevent admins from locking themselves out or demoting themselves
    if user_id == current_user.id and (
        payload.is_active is False or payload.role not in (None, current_user.role)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot disable or demote themselves.",
        )

    # Prevent the last active admin from being demoted or deactivated
    if (
        user.role == Role.ADMIN
        and user.is_active
        and (payload.role not in (None, Role.ADMIN) or payload.is_active is False)
        and _active_admin_count(repository) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one active admin is required.",
        )

    email = payload.email or user.email
    existing = repository.get_by_email(email)
    if existing and existing.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered."
        )
    target_role = payload.role or user.role
    if target_role == Role.STUDENT:
        student_number = payload.student_number or user.student_number
        existing_number = (
            repository.get_by_student_number(student_number)
            if student_number is not None
            else None
        )
        if existing_number and existing_number.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Student number is already registered.",
            )
        if student_number is not None and user.student_number != student_number:
            try:
                user = repository.set_student_number(user_id, student_number) or user
            except (UniqueViolation, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Student number is already registered.",
                ) from exc

    updated = repository.update_user(
        user_id,
        email,
        payload.full_name or user.full_name,
        target_role,
        payload.is_active if payload.is_active is not None else user.is_active,
    )
    append_action_audit(
        action_audits,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="update_user",
        target_type="user",
        target_id=user_id,
        details={"email": email, "role": (payload.role or user.role).value, "is_active": payload.is_active if payload.is_active is not None else user.is_active},
    )
    return user_response(updated)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_managed_user_password(
    user_id: str,
    payload: AdminPasswordReset,
    current_admin: Annotated[UserRecord, Depends(require_admin)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
    notification_service: Annotated[SMTPNotificationService, Depends(get_notification_service)],
) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    updated = reset_password(repository, user_id, payload.password, must_change_password=True)
    append_action_audit(
        action_audits,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        action="reset_password",
        target_type="user",
        target_id=user_id,
        details={"email": user.email, "role": user.role.value, "must_change_password": True},
    )
    send_password_setup_email(updated, notification_service)
    return user_response(updated)


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_managed_user(
    user_id: str,
    current_admin: Annotated[UserRecord, Depends(require_admin)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> UserResponse:
    """
    Soft-deletes a user by setting is_active = False and cleaning up all
    live memberships atomically.

    Cascade behaviour by role:
      STUDENT    → removed from every project group and course enrolment.
      INSTRUCTOR → removed from every course instructor assignment.
                   Their courses and projects are kept (created_by preserved).
      ADMIN      → deactivated only; no project / course roles to clean up.

    Historical data (assessments, commits, audit logs) is never removed —
    the user row stays in the DB so FK references remain valid.

    NOTE: ProjectRepository must implement unassign_instructor(course_id, user_id).
    Add it to your repository interface and both implementations:

      In-memory:
        def unassign_instructor(self, course_id: str, user_id: str) -> None:
            self._instructor_assignments.discard((course_id, user_id))

      PostgreSQL:
        def unassign_instructor(self, course_id: str, user_id: str) -> None:
            self._conn.execute(
                "DELETE FROM course_instructors WHERE course_id = %s AND user_id = %s",
                (course_id, user_id),
            )
    """
    user = users.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot disable themselves.",
        )

    if (
        user.role == Role.ADMIN
        and user.is_active
        and _active_admin_count(users) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one active admin is required.",
        )

    # Soft-delete + cascade membership cleanup
    updated = deactivate_user_cascade(users, projects, user_id)
    append_action_audit(
        action_audits,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        action="deactivate_user",
        target_type="user",
        target_id=user_id,
        details={"email": updated.email, "role": updated.role.value},
    )
    return user_response(updated)


@router.post("/{user_id}/activate", response_model=UserResponse)
def activate_managed_user(
    user_id: str,
    current_admin: Annotated[UserRecord, Depends(require_admin)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
    action_audits: Annotated[ActionAuditRepository, Depends(get_action_audit_repository)],
) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active.",
        )

    updated = repository.update_user(
        user_id,
        user.email,
        user.full_name,
        user.role,
        True,
    )
    append_action_audit(
        action_audits,
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        action="activate_user",
        target_type="user",
        target_id=user_id,
        details={"email": updated.email, "role": updated.role.value},
    )
    return user_response(updated)