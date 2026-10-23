from pydantic import BaseModel, Field


class StudentImportResult(BaseModel):
    course_id: str
    total_rows: int = Field(ge=0)
    created_students: int = Field(ge=0)
    enrolled_students: int = Field(ge=0)
    already_enrolled: int = Field(ge=0)
    notifications_suppressed: bool = False
