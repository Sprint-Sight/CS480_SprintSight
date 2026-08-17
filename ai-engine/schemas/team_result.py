from pydantic import BaseModel, Field

class TeamResult(BaseModel):
    code_quality: int = Field(ge=1, le=10)
    testing: int = Field(ge=1, le=10)
    documentation: int = Field(ge=1, le=10)
    requirements: int = Field(ge=1, le=10)
    collaboration: int = Field(ge=1, le=10) 