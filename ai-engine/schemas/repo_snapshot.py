from pydantic import BaseModel, Field


class SnapshotFile(BaseModel):
    path: str
    size_bytes: int = Field(default=0, ge=0)
    # None when the content was not captured (binary, over the backend's
    # per-file cap, or past its total-size cap).
    line_count: int | None = None
    content: str | None = None


class RepoSnapshot(BaseModel):
    """The repository's tracked files at the submitted HEAD, as read by the
    backend (gitlabGithub.collect_repository_snapshot). Lets the evaluator
    grade the final submission, not only the commit history."""
    head_sha: str | None = None
    files: list[SnapshotFile] = Field(default_factory=list)
    truncated: bool = False
    omitted_noise_files: int = 0
