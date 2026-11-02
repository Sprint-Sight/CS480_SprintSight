from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.assessment import JiraTicket

ExternalSource = Literal["github", "gitlab", "bitbucket", "jira"]


class EvidenceTarget(BaseModel):
    """The artifact one evidence citation points at."""
    type: Literal["file", "commit", "ticket"]
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    # Commit the file is pinned to. None means the repository's current HEAD
    # (older citations that never recorded the graded commit).
    commit_sha: str | None = None
    ticket_id: str | None = None


class EvidenceLink(BaseModel):
    # Same display string as the report's evidence_citations[i], so a client
    # can swap its plain-text list for this one without re-formatting.
    citation: str
    identifier: str
    reason: str = ""
    kind: str = "other"
    target: EvidenceTarget | None = None
    # Path under the API prefix (e.g. "/artifacts/projects/p1/file?path=...")
    # that returns the artifact for an in-app viewer. None when the artifact
    # cannot be read from inside SprintSight (e.g. no local repository).
    viewer_path: str | None = None
    # Deep link to GitHub/GitLab/Bitbucket/Jira when one can be worked out.
    external_url: str | None = None
    external_source: ExternalSource | None = None


class ReportEvidenceLinksResponse(BaseModel):
    report_id: str
    course_id: str
    project_id: str
    sprint_id: str
    # Keyed by rubric dimension, in the same order as each dimension's
    # evidence_citations.
    dimensions: dict[str, list[EvidenceLink]] = Field(default_factory=dict)


class ArtifactFileLine(BaseModel):
    number: int
    text: str


class ArtifactFileView(BaseModel):
    project_id: str
    file_path: str
    commit_sha: str
    total_lines: int
    # The lines returned: the whole file when it is small, otherwise a window
    # around the highlighted range (see first_line/last_line).
    lines: list[ArtifactFileLine]
    first_line: int
    last_line: int
    highlight_start: int | None = None
    highlight_end: int | None = None
    is_binary: bool = False
    truncated: bool = False
    external_url: str | None = None
    external_source: ExternalSource | None = None


class ArtifactCommitFile(BaseModel):
    filename: str
    change_type: Literal["added", "modified", "deleted", "renamed"] = "modified"
    lines_added: int = 0
    lines_deleted: int = 0
    diff: str | None = None
    diff_truncated: bool = False


class ArtifactCommitView(BaseModel):
    project_id: str
    commit_sha: str
    author: str
    author_email: str | None = None
    timestamp: datetime
    message: str
    parent_shas: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_deleted: int = 0
    files_changed: list[ArtifactCommitFile] = Field(default_factory=list)
    external_url: str | None = None
    external_source: ExternalSource | None = None


class ArtifactTicketView(BaseModel):
    project_id: str
    ticket: JiraTicket
    # When the ingested snapshot holding this ticket was captured, so a viewer
    # can tell the reader how fresh the details are.
    captured_at: datetime
    sprint_id: str
    external_url: str | None = None
    external_source: ExternalSource | None = None
