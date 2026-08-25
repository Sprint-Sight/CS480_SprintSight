from app.repositories.in_memory import manual_text_repo
from app.schemas.assessment import ManualTextPayload


def upsert_manual_text(payload: ManualTextPayload, updated_by: str) -> None:
    manual_text_repo.upsert(payload, updated_by)


def get_manual_text(course_id: str, project_id: str, sprint_id: str) -> str | None:
    return manual_text_repo.get(course_id, project_id, sprint_id)
