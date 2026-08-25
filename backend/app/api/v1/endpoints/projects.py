from typing import Annotated
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import get_project_repository, get_user_repository, require_admin, require_faculty, get_current_user
from app.repositories.interfaces import ProjectRecord, ProjectRepository, UserRecord, UserRepository
from app.schemas.auth import Role, UserResponse
from app.schemas.projects import CourseCreate, CourseInstructorResponse, CourseResponse, InstructorStudentCreate, ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.authService.service import create_user, user_response

router = APIRouter(tags=["courses", "projects"])


def _course_or_404(repository: ProjectRepository, course_id: str):
    course = repository.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found.")
    return course


def _can_manage_course(user: UserRecord, course_id: str, repository: ProjectRepository) -> bool:
    return user.role == Role.INSTRUCTOR and repository.is_instructor_assigned(course_id, user.id)


def _project_response(project: ProjectRecord, project_repository: ProjectRepository, user_repository: UserRepository) -> ProjectResponse:
    members = []
    for member_id in project_repository.list_member_ids(project.id):
        member = user_repository.get_by_id(member_id)
        if member:
            members.append(user_response(member))
    return ProjectResponse(id=project.id, project_name=project.project_name, description=project.description,
                           course_code=project.course_code, github_repo_url=project.github_repo_url,
                           created_by=project.created_by, created_at=project.created_at, members=members)


@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(payload: CourseCreate, current_user: Annotated[UserRecord, Depends(require_faculty)], repository: Annotated[ProjectRepository, Depends(get_project_repository)]) -> CourseResponse:
    if any(course.code.lower() == payload.code.lower() and course.section.lower() == payload.section.lower()
           and course.year == payload.year and course.term.lower() == payload.term.lower()
           for course in repository.list_courses()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Course offering already exists.")
    course = repository.create_course(payload.code, payload.name, payload.section, payload.year, payload.term, current_user.id)
    return CourseResponse(id=course.id, code=course.code, name=course.name, section=course.section,
                          year=course.year, term=course.term, created_by=course.created_by,
                          created_at=course.created_at)


@router.get("/courses", response_model=list[CourseResponse])
def list_courses(_: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[ProjectRepository, Depends(get_project_repository)]) -> list[CourseResponse]:
    return [CourseResponse(id=course.id, code=course.code, name=course.name, section=course.section,
                           year=course.year, term=course.term, created_by=course.created_by,
                           created_at=course.created_at) for course in repository.list_courses()]


@router.post("/courses/{course_id}/instructors/{user_id}", response_model=CourseInstructorResponse)
def assign_instructor(course_id: str, user_id: str, _: Annotated[UserRecord, Depends(require_admin)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> CourseInstructorResponse:
    _course_or_404(repository, course_id)
    user = users.get_by_id(user_id)
    if not user or user.role != Role.INSTRUCTOR:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An active instructor account is required.")
    repository.assign_instructor(course_id, user_id)
    return CourseInstructorResponse(course_id=course_id, user_id=user_id, role=user.role)


@router.post("/courses/{course_id}/students", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_course_student(course_id: str, payload: InstructorStudentCreate, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> UserResponse:
    _course_or_404(repository, course_id)
    if current_user.role != Role.ADMIN and not repository.is_instructor_assigned(course_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    return user_response(create_user(users, payload.email, payload.full_name, Role.STUDENT, payload.password))


@router.post("/students", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: InstructorStudentCreate,
    current_user: Annotated[UserRecord, Depends(require_faculty)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    return user_response(create_user(users, payload.email, payload.full_name, Role.STUDENT, payload.password))


@router.post("/courses/{course_id}/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(course_id: str, payload: ProjectCreate, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    course = _course_or_404(repository, course_id)
    if not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor is not assigned to this course.")
    members = []
    for member_id in payload.member_ids:
        member = users.get_by_id(member_id)
        if not member or member.role != Role.STUDENT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project members must be students.")
        members.append(member_id)
    project = ProjectRecord(str(uuid4()), payload.project_name, payload.description, course_id, course.code, payload.github_repo_url, current_user.id, datetime.now(timezone.utc))
    repository.create_project(project, members)
    return _project_response(project, repository, users)


@router.get("/courses/{course_id}/projects", response_model=list[ProjectResponse])
def list_projects(course_id: str, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> list[ProjectResponse]:
    _course_or_404(repository, course_id)
    projects = repository.list_projects(course_id)
    if current_user.role == Role.STUDENT:
        projects = [project for project in projects if current_user.id in repository.list_member_ids(project.id)]
    elif not _can_manage_course(current_user, course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this course.")
    return [_project_response(project, repository, users) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if current_user.role != Role.STUDENT and not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    if current_user.role == Role.STUDENT and current_user.id not in repository.list_member_ids(project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    return _project_response(project, repository, users)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, payload: ProjectUpdate, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    updated = repository.update_project(project_id, payload.project_name or project.project_name, payload.description, payload.github_repo_url)
    return _project_response(updated, repository, users)


@router.delete("/projects/{project_id}", response_model=ProjectResponse)
def delete_project(project_id: str, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    if not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    repository.delete_project(project_id)
    return _project_response(project, repository, users)


@router.post("/projects/{project_id}/members/{user_id}", response_model=ProjectResponse)
def add_member(project_id: str, user_id: str, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    project = repository.get_project(project_id)
    member = users.get_by_id(user_id)
    if not project or not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    if not member or member.role != Role.STUDENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project members must be students.")
    repository.set_members(project_id, repository.list_member_ids(project_id) + [user_id])
    return _project_response(project, repository, users)


@router.delete("/projects/{project_id}/members/{user_id}", response_model=ProjectResponse)
def remove_member(project_id: str, user_id: str, current_user: Annotated[UserRecord, Depends(get_current_user)], repository: Annotated[ProjectRepository, Depends(get_project_repository)], users: Annotated[UserRepository, Depends(get_user_repository)]) -> ProjectResponse:
    project = repository.get_project(project_id)
    if not project or not _can_manage_course(current_user, project.course_id, repository):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this project.")
    repository.set_members(project_id, [member_id for member_id in repository.list_member_ids(project_id) if member_id != user_id])
    return _project_response(project, repository, users)