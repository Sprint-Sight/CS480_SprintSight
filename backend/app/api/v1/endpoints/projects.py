from typing import Annotated
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation

from app.dependencies.auth import (
    get_assessment_repository,
    get_jira_ingestion_repository,
    get_project_repository,
    get_user_repository,
    require_admin,
    require_faculty,
    require_instructor,
    get_current_user,
)
from app.core.credential_crypto import encrypt_secret
from app.repositories.interfaces import AssessmentRepository, ProjectRecord, ProjectRepository, UserRecord, UserRepository
from app.schemas.assessment import AssessmentReport
from app.services.auditLogService.service import append_action_audit
from app.schemas.auth import Role, UserResponse
from app.schemas.projects import (
    CourseCreate,
    CourseInstructorResponse,
    CourseResponse,
    CourseUpdate,
    InstructorStudentCreate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.authService.service import create_user, user_response

router = APIRouter(tags=["courses", "projects"])


def _course_or_404(repository: ProjectRepository, course_id: str):
    course = repository.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return course


def _can_manage_course(user: UserRecord, course_id: str, repository: ProjectRepository) -> bool:
    return user.role == Role.INSTRUCTOR and repository.is_instructor_assigned(course_id, user.id)


def _project_response(
    project: ProjectRecord, project_repository: ProjectRepository, user_repository: UserRepository
) -> ProjectResponse:
    members = []
    for member_id in project_repository.list_member_ids(project.id):
        member = user_repository.get_by_id(member_id)
        if member:
            members.append(user_response(member))
    return ProjectResponse(
        id=project.id,
        project_name=project.project_name,
        description=project.description,
        team_name=project.team_name,
        course_code=project.course_code,
        github_repo_url=project.github_repo_url,
        local_repo_path=project.local_repo_path,
        jira_email=project.jira_email,
        jira_domain=project.jira_domain,
        jira_project_key=project.jira_project_key,
        jira_token_configured=bool(project.jira_api_token_encrypted),
        created_by=project.created_by,
        created_at=project.created_at,
        members=members,
    )


def _encrypted_jira_token(new_token: str | None, existing_encrypted: str | None, replace_token: bool) -> str | None:
    if not replace_token:
        return existing_encrypted
    if not new_token:
        return None
    return encrypt_secret(new_token)


def _validate_student_course_enrollment(repository: ProjectRepository, course_id: str, user_id: str):
    """Enforce: 1 student can only be enrolled in 1 section of a course code per term/year."""
    target_course = repository.get_course(course_id)
    if not target_course:
        return

    # Check all courses matching the code, year, and term
    for course in repository.list_courses():
        if (
            course.code.lower() == target_course.code.lower()
            and course.year == target_course.year
            and course.term.lower() == target_course.term.lower()
        ):
            if repository.is_student_enrolled(course.id, user_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Student is already enrolled in section '{course.section}' for {course.code} ({course.term} {course.year}).",
                )


def _validate_student_project_assignment(repository: ProjectRepository, course_id: str, user_id: str, current_project_id: str | None = None):
    """Enforce: 1 student can only belong to 1 project group in a given course."""
    existing_projects = repository.list_projects(course_id)
    for project in existing_projects:
        if current_project_id and project.id == current_project_id:
            continue
        if user_id in repository.list_member_ids(project.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Student is already assigned to group '{project.team_name}' in this course.",
            )


# ---------------------------------------------------------------------------
# Course Endpoints
# ---------------------------------------------------------------------------

@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> CourseResponse:
    if any(
        course.code.lower() == payload.code.lower()
        and course.section.lower() == payload.section.lower()
        and course.year == payload.year
        and course.term.lower() == payload.term.lower()
        for course in repository.list_courses()
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course offering already exists.")
    course = repository.create_course(payload.code, payload.name, payload.section, payload.year, payload.term, current_user.id)
    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="create_course",
        target_type="course",
        target_id=course.id,
        details={
            "code": course.code,
            "section": course.section,
            "year": course.year,
            "term": course.term,
        },
    )
    return CourseResponse(
        id=course.id,
        code=course.code,
        name=course.name,
        section=course.section,
        year=course.year,
        term=course.term,
        created_by=course.created_by,
        created_at=course.created_at,
    )


@router.get("/courses", response_model=list[CourseResponse])
def list_courses(
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> list[CourseResponse]:
    if current_user.role == Role.STUDENT:
        courses = [course for course in repository.list_courses() if repository.is_student_enrolled(course.id, current_user.id)]
    elif current_user.role == Role.INSTRUCTOR:
        courses = [course for course in repository.list_courses() if repository.is_instructor_assigned(course.id, current_user.id)]
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to courses.")
    return [
        CourseResponse(
            id=course.id,
            code=course.code,
            name=course.name,
            section=course.section,
            year=course.year,
            term=course.term,
            created_by=course.created_by,
            created_at=course.created_at,
        )
        for course in courses
    ]


@router.get("/courses/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> CourseResponse:
    course = _course_or_404(repository, course_id)
    if not repository.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this course.")
    return CourseResponse(
        id=course.id,
        code=course.code,
        name=course.name,
        section=course.section,
        year=course.year,
        term=course.term,
        created_by=course.created_by,
        created_at=course.created_at,
    )


@router.patch("/courses/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: str,
    payload: CourseUpdate,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> CourseResponse:
    course = _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an assigned instructor can manage this course.")
    code = payload.code or course.code
    section = payload.section or course.section
    year = payload.year or course.year
    term = payload.term or course.term
    if any(
        existing.id != course_id
        and existing.code.lower() == code.lower()
        and existing.section.lower() == section.lower()
        and existing.year == year
        and existing.term.lower() == term.lower()
        for existing in repository.list_courses()
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course offering already exists.")
    updated = repository.update_course(course_id, code, payload.name or course.name, section, year, term)
    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="update_course",
        target_type="course",
        target_id=course_id,
        details={"code": code, "section": section, "year": year, "term": term},
    )
    return CourseResponse(
        id=updated.id,
        code=updated.code,
        name=updated.name,
        section=updated.section,
        year=updated.year,
        term=updated.term,
        created_by=updated.created_by,
        created_at=updated.created_at,
    )


@router.delete("/courses/{course_id}", response_model=CourseResponse)
def delete_course(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> CourseResponse:
    course = _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an assigned instructor can manage this course.")
    repository.delete_course(course_id)
    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="delete_course",
        target_type="course",
        target_id=course_id,
        details={"code": course.code, "section": course.section, "year": course.year, "term": course.term},
    )
    return CourseResponse(
        id=course.id,
        code=course.code,
        name=course.name,
        section=course.section,
        year=course.year,
        term=course.term,
        created_by=course.created_by,
        created_at=course.created_at,
    )


@router.get("/courses/{course_id}/students", response_model=list[UserResponse])
def list_course_students(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> list[UserResponse]:
    _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned instructor can view this roster.")
    return [user_response(user) for user_id in repository.list_enrolled_student_ids(course_id) if (user := users.get_by_id(user_id))]


@router.post("/courses/{course_id}/students/{user_id}", response_model=UserResponse)
def enroll_course_student(
    course_id: str,
    user_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned instructor can enroll students.")
    user = users.get_by_id(user_id)
    if not user or user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only student accounts can be enrolled.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot enroll a disabled user account.")

    # Enforce 1 section per course rule
    _validate_student_course_enrollment(repository, course_id, user_id)

    try:
        if not repository.enroll_student(course_id, user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already enrolled in this course section.")
    except UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Student is already enrolled in a section for this course."
        ) from exc

    return user_response(user)


@router.delete("/courses/{course_id}/students/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unenroll_course_student(
    course_id: str,
    user_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> None:
    _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the assigned instructor can unenroll students.")
    if not repository.unenroll_student(course_id, user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not enrolled in this course.")


@router.post("/courses/{course_id}/instructors/{user_id}", response_model=CourseInstructorResponse)
def assign_instructor(
    course_id: str,
    user_id: str,
    current_user: Annotated[UserRecord, Depends(require_instructor)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> CourseInstructorResponse:
    _course_or_404(repository, course_id)
    if not repository.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")

    user = users.get_by_id(user_id)
    if not user or user.role not in (Role.INSTRUCTOR, Role.ADMIN):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An active instructor, admin, or TA account is required.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign a disabled user account.")
    repository.assign_instructor(course_id, user_id)
    return CourseInstructorResponse(course_id=course_id, user_id=user_id, role=user.role)


@router.post("/courses/{course_id}/students", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_course_student(
    course_id: str,
    payload: InstructorStudentCreate,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    _course_or_404(repository, course_id)
    if current_user.role != Role.INSTRUCTOR or not repository.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor or TA is not assigned to this course.")

    existing_user = users.get_by_email(payload.email)
    if existing_user:
        if existing_user.role != Role.STUDENT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")
        if not existing_user.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot enroll a disabled user account.")
        student = existing_user
    else:
        try:
            student = create_user(users, payload.email, payload.full_name, Role.STUDENT, payload.password)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_409_CONFLICT:
                raise
            existing_user = users.get_by_email(payload.email)
            if not existing_user or existing_user.role != Role.STUDENT:
                raise
            student = existing_user

    if repository.is_student_enrolled(course_id, student.id):
        return user_response(student)

    _validate_student_course_enrollment(repository, course_id, student.id)

    if not repository.enroll_student(course_id, student.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student is already enrolled in this course section.")
    return user_response(student)


# ---------------------------------------------------------------------------
# Project Endpoints
# ---------------------------------------------------------------------------

@router.post("/courses/{course_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    course_id: str,
    payload: ProjectCreate,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    course = _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    if any(project.team_name.casefold() == payload.team_name.casefold() for project in repository.list_projects(course_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name already exists in this course.")

    members = []
    for member_id in payload.member_ids:
        member = users.get_by_id(member_id)
        if not member or member.role != Role.STUDENT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project members must be students.")
        if not member.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add a disabled user to a project.")
        if not repository.is_student_enrolled(course_id, member_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Students must be enrolled in the course before joining a project.")

        # Enforce 1 group per course rule
        _validate_student_project_assignment(repository, course_id, member_id)
        members.append(member_id)

    project = ProjectRecord(
        id=str(uuid4()),
        project_name=payload.project_name,
        team_name=payload.team_name,
        description=payload.description,
        course_id=course_id,
        course_code=course.code,
        github_repo_url=payload.github_repo_url,
        local_repo_path=payload.local_repo_path,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
        jira_email=str(payload.jira_email) if payload.jira_email else None,
        jira_domain=payload.jira_domain,
        jira_project_key=payload.jira_project_key,
        jira_api_token_encrypted=_encrypted_jira_token(payload.jira_api_token, None, True),
    )
    try:
        repository.create_project(project, members)
    except UniqueViolation as exc:
        err_msg = str(exc)
        if "uq_student_single_project_per_course" in err_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A student is already assigned to another project in this course.") from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name or project parameters conflict with existing records.") from exc

    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="create_project",
        target_type="project",
        target_id=project.id,
        details={"team_name": project.team_name, "course_id": course_id},
    )
    return _project_response(project, repository, users)


@router.get("/courses/{course_id}/projects", response_model=list[ProjectResponse])
def list_projects(
    course_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> list[ProjectResponse]:
    _course_or_404(repository, course_id)
    projects = repository.list_projects(course_id)
    if current_user.role == Role.STUDENT:
        projects = [project for project in projects if current_user.id in repository.list_member_ids(project.id)]
    elif not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this course.")
    return [_project_response(project, repository, users) for project in projects]


@router.get("/students/courses", response_model=list[CourseResponse])
def list_student_courses(
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> list[CourseResponse]:
    if current_user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint is for students only.")
    courses = [course for course in repository.list_courses() if repository.is_student_enrolled(course.id, current_user.id)]
    return [
        CourseResponse(
            id=course.id,
            code=course.code,
            name=course.name,
            section=course.section,
            year=course.year,
            term=course.term,
            created_by=course.created_by,
            created_at=course.created_at,
        )
        for course in courses
    ]


@router.get("/students/projects", response_model=list[ProjectResponse])
def list_student_projects(
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> list[ProjectResponse]:
    if current_user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint is for students only.")

    projects: list[ProjectRecord] = []
    for course in repository.list_courses():
        if not repository.is_student_enrolled(course.id, current_user.id):
            continue
        projects.extend(
            project for project in repository.list_projects(course.id) if current_user.id in repository.list_member_ids(project.id)
        )
    return [_project_response(project, repository, users) for project in projects]


@router.get("/students/projects/{project_id}", response_model=ProjectResponse)
def get_student_project(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint is for students only.")
    if current_user.id not in repository.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    return _project_response(project, repository, users)


@router.get("/students/projects/{project_id}/reports", response_model=list[AssessmentReport])
def list_student_project_reports(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
) -> list[AssessmentReport]:
    if current_user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint is for students only.")

    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.id not in repository.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")

    if assessment_repository is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Assessment repository unavailable.")
    return assessment_repository.list_project_reports(project.course_id, project.id) or []


@router.get("/students/projects/{project_id}/sprints", response_model=list[str])
def list_student_project_sprints(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    assessment_repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    jira_runs_repo: Annotated[object, Depends(get_jira_ingestion_repository)],
) -> list[str]:
    if current_user.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This endpoint is for students only.")

    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.id not in repository.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")

    sprint_ids: set[str] = set()
    if assessment_repository is not None:
        for report in assessment_repository.list_project_reports(project.course_id, project.id) or []:
            if report.sprint_id:
                sprint_ids.add(report.sprint_id)
    for run in jira_runs_repo.list_project_runs(project_id):
        if run.sprint_id:
            sprint_ids.add(run.sprint_id)
    return sorted(sprint_ids)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.role != Role.STUDENT and not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    if current_user.role == Role.STUDENT and current_user.id not in repository.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    return _project_response(project, repository, users)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")

    sent = payload.model_fields_set

    def _resolve(field: str, existing):
        return getattr(payload, field) if field in sent else existing

    project_name = _resolve("project_name", project.project_name)
    team_name = _resolve("team_name", project.team_name)

    if team_name != project.team_name and any(
        existing.id != project_id and existing.team_name.casefold() == team_name.casefold()
        for existing in repository.list_projects(project.course_id)
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Team name already exists in this course.")

    description = _resolve("description", project.description)
    github_url = _resolve("github_repo_url", project.github_repo_url)
    local_path = _resolve("local_repo_path", project.local_repo_path)
    jira_email = str(payload.jira_email) if "jira_email" in sent and payload.jira_email else _resolve("jira_email", project.jira_email)
    jira_domain = _resolve("jira_domain", project.jira_domain)
    jira_key = _resolve("jira_project_key", project.jira_project_key)

    new_encrypted_token = _encrypted_jira_token(
        payload.jira_api_token,
        project.jira_api_token_encrypted,
        replace_token="jira_api_token" in sent,
    )

    try:
        updated = repository.update_project(
            project_id,
            project_name,
            team_name,
            description,
            github_url,
            local_path,
            jira_email,
            jira_domain,
            jira_key,
            new_encrypted_token,
        )
    except UniqueViolation as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project fields conflict with an existing project.") from exc

    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="update_project",
        target_type="project",
        target_id=project_id,
        details={
            "project_name": project_name,
            "team_name": team_name,
            "course_id": project.course_id,
            "jira_project_key": jira_key,
        },
    )
    return _project_response(updated, repository, users)


@router.delete("/projects/{project_id}", response_model=ProjectResponse)
def delete_project(
    project_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")

    deleted = repository.delete_project(project_id)
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="delete_project",
        target_type="project",
        target_id=project_id,
        details={"team_name": project.team_name, "course_id": project.course_id},
    )
    return _project_response(project, repository, users)


@router.post("/projects/{project_id}/members/{user_id}", response_model=ProjectResponse)
def add_member(
    project_id: str,
    user_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    member = users.get_by_id(user_id)
    if not project or not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    if not member or member.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project members must be students.")
    if not member.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add a disabled user to a project.")
    if not repository.is_student_enrolled(project.course_id, user_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student must be enrolled in the course before joining a project.")

    # Enforce 1 group per course rule
    _validate_student_project_assignment(repository, project.course_id, user_id, current_project_id=project_id)

    try:
        repository.set_members(project_id, repository.list_member_ids(project_id) + [user_id])
    except UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Student is already assigned to a project group in this course."
        ) from exc

    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="add_project_member",
        target_type="project_member",
        target_id=user_id,
        details={"project_id": project_id, "course_id": project.course_id},
    )
    return _project_response(project, repository, users)


@router.delete("/projects/{project_id}/members/{user_id}", response_model=ProjectResponse)
def remove_member(
    project_id: str,
    user_id: str,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project or not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")

    current_members = repository.list_member_ids(project_id)
    if user_id not in current_members:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not a member of this project.")

    repository.set_members(project_id, [m_id for m_id in current_members if m_id != user_id])
    append_action_audit(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="remove_project_member",
        target_type="project_member",
        target_id=user_id,
        details={"project_id": project_id, "course_id": project.course_id},
    )
    return _project_response(project, repository, users)  