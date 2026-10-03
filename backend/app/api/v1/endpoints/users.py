# app/routers/users.py

from app.core.security import hash_password
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import (
    get_project_repository,
    get_user_repository,
    require_admin,
    require_faculty,
)
from app.repositories.interfaces import (
    ProjectRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.auth import (
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserUpdate,
    PasswordChangeRequest, #for reset password unsafe
    Role,
    UserResponse,
)
from app.services.auditLogService.service import append_action_audit
from app.services.authService.deactivation import deactivate_user_cascade
from app.services.authService.service import create_user, reset_password, user_response

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Who can create whom?
#
#   Admin      → POST /users with any role (instructor, student, admin)
#   Instructor → POST /courses/{id}/students   (creates + enrols in one step)
#                POST /students                 (creates without enrolment)
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
        users = [u for u in users if u.role == Role.STUDENT and u.is_active]
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
    if current_user.role == Role.INSTRUCTOR and (user.role != Role.STUDENT or not user.is_active):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructors can only view student accounts.")
    return user_response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_managed_user(
    payload: AdminUserCreate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """
    Admin creates any account type (instructor / student / admin).
    Instructors may only create student accounts.
    """
    if current_user.role == Role.INSTRUCTOR and payload.role != Role.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructors can only create student accounts.",
        )
    created = create_user(repository, payload.email, payload.full_name, payload.role, payload.password)
    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="create_user",
        target_type="user",
        target_id=created.id,
        details={"email": created.email, "role": created.role.value},
    )
    return user_response(created)


@router.patch("/{user_id}", response_model=UserResponse)
def update_managed_user(
    user_id: str,
    payload: AdminUserUpdate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
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

    updated = repository.update_user(
        user_id,
        email,
        payload.full_name or user.full_name,
        payload.role or user.role,
        payload.is_active if payload.is_active is not None else user.is_active,
    )
    append_action_audit(
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
) -> UserResponse:
    user = repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    updated = reset_password(repository, user_id, payload.password, must_change_password=True)
    append_action_audit(
        actor_id=current_admin.id,
        actor_role=current_admin.role.value,
        action="reset_password",
        target_type="user",
        target_id=user_id,
        details={"email": user.email, "role": user.role.value, "must_change_password": True},
    )
    return user_response(updated)


@router.post("/change-password", response_model=UserResponse)
def change_own_password(
    payload: PasswordChangeRequest,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """
    Self-service password change/reset (forgot-password flow).
    Identifies the account by email instead of user_id, since a user
    who forgot their password only knows their email, not their
    internal user_id. This also matches the future OTP flow, where
    email is the natural first input (OTP gets sent there).
    """
    user = repository.get_by_email(payload.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    updated = repository.update_password(user.id, hash_password(payload.password), False)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return user_response(updated)


@router.delete("/{user_id}", response_model=UserResponse)
def deactivate_managed_user(
    user_id: str,
    current_admin: Annotated[UserRecord, Depends(require_admin)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    projects: Annotated[ProjectRepository, Depends(get_project_repository)],
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
    _: Annotated[UserRecord, Depends(require_admin)],
    repository: Annotated[UserRepository, Depends(get_user_repository)],
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
    return user_response(updated)