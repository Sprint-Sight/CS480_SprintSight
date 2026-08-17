from pydantic import BaseModel, Field

class CommitInfo(BaseModel): # Define Github commit info
    author: str = Field(description="Student handle or name")
    message: str = Field(description="Commit message text")
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)