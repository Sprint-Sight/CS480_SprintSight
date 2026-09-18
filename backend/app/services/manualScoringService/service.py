from fastapi import HTTPException, status

from app.repositories.interfaces import ProjectRepository, UserRecord
from app.repositories.manual_override import ManualOverrideRecord, ManualOverrideRepository
from app.schemas.manual_scoring import ManualOverrideCreate


class ManualScoringService:
    def __init__(self, repository: ManualOverrideRepository, projects: ProjectRepository) -> None:
        self._repository = repository
        self._projects = projects

    def create_or_update(
        self, payload: ManualOverrideCreate, user: UserRecord
    ) -> ManualOverrideRecord:
        project = self._projects.get_project(payload.project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        if project.course_id != payload.course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project does not belong to course.",
            )
        if not self._projects.is_instructor_assigned(project.course_id, user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Instructor is not assigned to this course.",
            )

        total_score = sum(
            (
                payload.requirements_score,
                payload.code_quality_score,
                payload.testing_score,
                payload.documentation_score,
                payload.collaboration_score,
                payload.cicd_score,
            )
        ) / 6
        return self._repository.upsert(
            course_id=payload.course_id,
            project_id=payload.project_id,
            sprint_id=payload.sprint_id,
            team_name=project.team_name,
            requirements_score=payload.requirements_score,
            code_quality_score=payload.code_quality_score,
            testing_score=payload.testing_score,
            documentation_score=payload.documentation_score,
            collaboration_score=payload.collaboration_score,
            cicd_score=payload.cicd_score,
            total_score=total_score,
            graded_by=user.id,
        )

    def list_overrides(
        self, *, course_id: str | None, project_id: str, sprint_id: str | None, user: UserRecord
    ) -> list[ManualOverrideRecord]:
        project = self._projects.get_project(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        if course_id is not None and project.course_id != course_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project does not belong to course.",
            )
        is_member = user.id in self._projects.list_member_ids(project_id)
        is_assigned = self._projects.is_instructor_assigned(project.course_id, user.id)
        if not is_member and not is_assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this project.",
            )
        return self._repository.list(
            course_id=project.course_id,
            project_id=project_id,
            sprint_id=sprint_id,
        )
