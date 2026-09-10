from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ManualOverrideCreate(BaseModel):
    course_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    sprint_id: str = Field(min_length=1, max_length=100)
    requirements_score: float = Field(ge=0, le=100)
    code_quality_score: float = Field(ge=0, le=100)
    testing_score: float = Field(ge=0, le=100)
    documentation_score: float = Field(ge=0, le=100)
    collaboration_score: float = Field(ge=0, le=100)


class ManualOverrideResponse(BaseModel):
    override_id: UUID
    course_id: str
    project_id: str
    sprint_id: str
    team_name: str
    requirements_score: float
    code_quality_score: float
    testing_score: float
    documentation_score: float
    collaboration_score: float
    total_score: float
    graded_by: str
    created_at: datetime
    updated_at: datetime
