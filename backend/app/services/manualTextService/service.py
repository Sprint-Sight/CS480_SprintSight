from app.repositories.interfaces import ManualTextRepository
from app.schemas.assessment import ManualTextPayload


def upsert_manual_text(repository: ManualTextRepository, payload: ManualTextPayload, updated_by: str) -> None:
    repository.upsert(payload, updated_by)


def get_manual_text(repository: ManualTextRepository, course_id: str, project_id: str, sprint_id: str) -> str | None:
    return repository.get(course_id, project_id, sprint_id)
