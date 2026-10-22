# app/services/authService/deactivation.py

from fastapi import HTTPException, status

from app.repositories.interfaces import ProjectRepository, UserRecord, UserRepository
from app.schemas.auth import Role


def deactivate_user_cascade(
    user_repository: UserRepository,
    project_repository: ProjectRepository,
    user_id: str,
) -> UserRecord:
    """
    Soft-delete a user and clean up every live membership in one operation.

    Role-based cleanup:
      STUDENT    → removed from every project group and every course enrolment.
      INSTRUCTOR → removed from every course instructor assignment.
                   Their created courses and projects are kept — created_by is
                   preserved so the audit trail stays intact.
      ADMIN      → no project or course roles to clean up; just deactivated.

    What is intentionally NOT touched (historical / audit data):
      - git_artifacts          (author_github is a plain string, no FK)
      - sprint_assessments     (team score history must survive)
      - individual_assessments (grade history must survive)
      - criterion_scores       (same)
      - instructor_reviews     (reviewer is recorded for audit)
      - audit_logs             (actor_id FK is ON DELETE SET NULL on hard delete;
                                here the row stays — the reference is valid because
                                we never hard-delete users)
    """
    user = user_repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.role == Role.STUDENT:
        _remove_student_memberships(user_id, project_repository)
    elif user.role == Role.INSTRUCTOR:
        _remove_instructor_assignments(user_id, project_repository)
    # ADMIN: no project / course memberships to clean up

    return user_repository.update_user(
        user_id,
        user.email,
        user.full_name,
        user.role,
        False,          # is_active = False → soft delete
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _remove_student_memberships(
    user_id: str,
    project_repository: ProjectRepository,
) -> None:
    """
    Remove a student from every project group and course enrolment.

    Iterates all courses so no extra repository method is required.
    For a large deployment, add list_project_ids_for_member() and
    list_course_ids_for_student() to the repository interface and replace
    the loops with those targeted queries.
    """
    for course in project_repository.list_courses():
        # ── 1. Drop from every project group within this course ───────────
        for project in project_repository.list_projects(course.id):
            current_members = project_repository.list_member_ids(project.id)
            if user_id in current_members:
                project_repository.set_members(
                    project.id,
                    [m for m in current_members if m != user_id],
                )

        # ── 2. Unenroll from the course itself ────────────────────────────
        # unenroll_student returns False if the student was not enrolled;
        # we ignore that — idempotency is fine here.
        project_repository.unenroll_student(course.id, user_id)


def _remove_instructor_assignments(
    user_id: str,
    project_repository: ProjectRepository,
) -> None:
    """
    Remove an instructor from every course they are assigned to.

    Requires ProjectRepository.unassign_instructor() — see the note in
    users.py about adding this method to your repository interface and
    both the in-memory and PostgreSQL implementations.
    """
    for course in project_repository.list_courses():
        if project_repository.is_instructor_assigned(course.id, user_id):
            project_repository.unassign_instructor(course.id, user_id)