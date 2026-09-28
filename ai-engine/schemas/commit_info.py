from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# LLM can see if commit touched readme file or test_auth without having to rely soley on the git commit message.
class FileDiff(BaseModel):
    filename: str = Field(description="Path of the changed file")
    change_type: Literal["added", "modified", "deleted", "renamed"] = "modified"
    lines_added: int = Field(default=0, ge=0)
    lines_deleted: int = Field(default=0, ge=0)

#sha provides exact ID the model needs for evidence citation
class CommitInfo(BaseModel):
    sha: str = Field(description="Commit hash — needed for evidence citations in rubric justifications")
    author: str = Field(description="Student handle or name")
    message: str = Field(description="Commit message text")
    timestamp: datetime = Field(description="When the commit was made")
    lines_added: int = Field(default=0, ge=0, description="Aggregate total, kept for quick-glance prompts")
    lines_deleted: int = Field(default=0, ge=0, description="Aggregate total, kept for quick-glance prompts")
    files_changed: list[FileDiff] = Field(default_factory=list)

    def __str__(self):
        return f"Git commit info: \n CommitInfo(sha={self.sha}, author={self.author}, message={self.message}, timestamp={self.timestamp}, lines_added={self.lines_added}, lines_deleted={self.lines_deleted}, files_changed={len(self.files_changed)} files, \n)"

    # # Populated by the preprocessing/mapping service after ingestion, not raw input
    # # Filter real Git history into specific sprint buckets before passing to LLM
    # resolved_sprint_id: Optional[str] = Field(default=None)
    # mapping_confidence: Optional[Literal["high", "low", "unmapped"]] = Field(default=None)

# class CommitInfo(BaseModel): # Define Github commit info
#     author: str = Field(description="Student handle or name")
#     message: str = Field(description="Commit message text")
#     lines_added: int = Field(default=0, ge=0)
#     lines_deleted: int = Field(default=0, ge=0)
#     # Add git diff stats if needed, e.g., files changed, etc. # Maybe define a separate model for git diff stats if we want to capture more granular info.
#     # Assume grade based on git commit message quality, lines added/deleted, an d other heuristics.
#     # Date time of commit can also be added if needed for further analysis.