"""Turns AI evidence citations into links a client can open.

Every citation gets up to two links:
- `viewer_path`: an /artifacts endpoint that returns the file, commit, or
  Jira ticket from SprintSight's own copy, pinned to the commit that was
  graded. Works for local-only repositories and needs no GitHub/Jira login.
- `external_url`: the same artifact on GitHub/GitLab/Bitbucket/Jira. The
  repository URL is the project's saved one, else the local clone's origin
  remote; Jira links need the project's Jira domain.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlencode, urlsplit

from app.core.config import get_settings
from app.core.credential_crypto import normalize_jira_domain
from app.repositories.interfaces import (
    JiraIngestionRunRecord,
    JiraIngestionRunRepository,
    ProjectRecord,
)
from app.schemas.artifacts import (
    ArtifactCommitFile,
    ArtifactCommitView,
    ArtifactFileLine,
    ArtifactFileView,
    ArtifactTicketView,
    EvidenceLink,
    EvidenceTarget,
    ReportEvidenceLinksResponse,
)
from app.schemas.assessment import AssessmentReport, EvidenceDetail
from app.services.gitlabGithub.service import (
    ArtifactNotFoundError,
    list_tracked_paths,
    read_commit,
    read_file_at_revision,
    repository_remote_url,
    resolve_commit,
    resolve_local_repository_path,
)

logger = logging.getLogger(__name__)

# Files up to this many lines are returned whole; longer ones are windowed
# around the cited range so a generated 20k-line file cannot stall the UI.
VIEWER_MAX_FILE_LINES = 2000
VIEWER_CONTEXT_LINES = 200
VIEWER_MAX_DIFF_CHARS_PER_FILE = 20000
VIEWER_MAX_DIFF_CHARS_PER_COMMIT = 200000

# Kept in step with ai-engine/services/grounding.py, which produced the
# identifiers parsed here for citations that carry no structured fields.
_LINE_ANCHOR = re.compile(
    r"(?P<path>[\w.@+\-/]+)(?::|#)L?(?P<start>\d+)(?:\s*[-–]\s*L?(?P<end>\d+))?"
    r"(?:\s*@\s*(?P<sha>[0-9a-fA-F]{7,40}))?"
)
_SHA = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
_TICKET = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_PATH_TOKEN = re.compile(r"[\w.@+\-]+(?:/[\w.@+\-]+)*")
_CITATION_SEPARATOR = " — "  # assessmentService._format_evidence_citations

RepositorySource = Literal["github", "gitlab", "bitbucket"]

# Per host: (file page, commit page) path segments after the repository URL.
_REPOSITORY_PAGES: dict[str, tuple[str, str]] = {
    "github": ("blob", "commit"),
    "gitlab": ("-/blob", "-/commit"),
    "bitbucket": ("src", "commits"),
}
# "git@github.com:org/repo.git" style remotes.
_SCP_REMOTE = re.compile(r"^[\w.\-]+@(?P<host>[\w.\-]+):(?P<path>[^\\]+)$")


@dataclass
class ArtifactLinkContext:
    project_id: str
    repository_url: str | None = None
    repository_source: RepositorySource | None = None
    jira_base_url: str | None = None
    jira_project_key: str | None = None
    has_local_repository: bool = False
    # Local clone's HEAD. External file links for citations that never
    # recorded a commit are pinned here rather than to the remote's moving HEAD.
    head_sha: str | None = None
    # Files tracked at HEAD. Used only to verify paths guessed from plain-text
    # citations; None when the repository could not be read.
    known_paths: set[str] | None = None
    known_tickets: set[str] = field(default_factory=set)


# ── External URLs ─────────────────────────────────────────────────────────


def repository_web_url(repo_url: str | None) -> tuple[str | None, RepositorySource | None]:
    if not repo_url:
        return None, None
    url = repo_url.strip().rstrip("/").removesuffix(".git")
    host = urlsplit(url).netloc.lower()
    if host == "github.com" or host.endswith(".github.com"):
        return url, "github"
    if "gitlab" in host:
        return url, "gitlab"
    if host == "bitbucket.org":
        return url, "bitbucket"
    return None, None


def remote_web_url(remote: str | None) -> str | None:
    """https://<host>/<owner>/<repo> for an HTTPS or SSH Git remote, or None
    for a local-path remote. Any credentials embedded in the remote (e.g.
    https://user:token@host/...) are dropped so they never reach a client."""
    if not remote:
        return None
    remote = remote.strip()
    if match := _SCP_REMOTE.match(remote):
        host, path = match.group("host"), match.group("path")
    else:
        parts = urlsplit(remote)
        if parts.scheme not in {"https", "http", "ssh", "git"} or not parts.hostname:
            return None
        host, path = parts.hostname, parts.path
    path = path.strip("/").removesuffix(".git")
    return f"https://{host.lower()}/{path}" if path else None


def jira_base_url(project: ProjectRecord) -> str | None:
    domain = normalize_jira_domain(project.jira_domain) or normalize_jira_domain(
        get_settings().jira_domain
    )
    return f"https://{domain}" if domain else None


def _line_fragment(source: RepositorySource | None, start: int, end: int) -> str:
    if source == "bitbucket":
        return f"#lines-{start}" if start == end else f"#lines-{start}:{end}"
    if start == end:
        return f"#L{start}"
    return f"#L{start}-L{end}" if source == "github" else f"#L{start}-{end}"


def file_url(context: ArtifactLinkContext, target: EvidenceTarget) -> str | None:
    if not context.repository_url or not context.repository_source or not target.file_path:
        return None
    ref = target.commit_sha or context.head_sha or "HEAD"
    path = quote(target.file_path, safe="/")
    file_page = _REPOSITORY_PAGES[context.repository_source][0]
    url = f"{context.repository_url}/{file_page}/{ref}/{path}"
    if target.line_start:
        url += _line_fragment(
            context.repository_source, target.line_start, target.line_end or target.line_start
        )
    return url


def commit_url(context: ArtifactLinkContext, commit_sha: str) -> str | None:
    if not context.repository_url or not context.repository_source:
        return None
    commit_page = _REPOSITORY_PAGES[context.repository_source][1]
    return f"{context.repository_url}/{commit_page}/{commit_sha}"


def ticket_url(context: ArtifactLinkContext, ticket_id: str) -> str | None:
    if not context.jira_base_url:
        return None
    return f"{context.jira_base_url}/browse/{quote(ticket_id, safe='')}"


# ── In-app viewer paths (relative to the API prefix) ──────────────────────


def file_viewer_path(project_id: str, target: EvidenceTarget) -> str:
    query = {"path": target.file_path}
    if target.commit_sha:
        query["ref"] = target.commit_sha
    if target.line_start:
        query["start"] = str(target.line_start)
        query["end"] = str(target.line_end or target.line_start)
    return f"/artifacts/projects/{quote(project_id, safe='')}/file?{urlencode(query)}"


def commit_viewer_path(project_id: str, commit_sha: str) -> str:
    return f"/artifacts/projects/{quote(project_id, safe='')}/commits/{commit_sha}"


def ticket_viewer_path(project_id: str, ticket_id: str) -> str:
    return f"/artifacts/projects/{quote(project_id, safe='')}/tickets/{quote(ticket_id, safe='')}"


# ── Citation → target ─────────────────────────────────────────────────────


def _match_known_path(candidate: str, known_paths: set[str]) -> str | None:
    candidate = candidate.strip().strip("`'\"").removeprefix("./").removeprefix("/")
    if candidate in known_paths:
        return candidate
    matches = [path for path in known_paths if path.endswith("/" + candidate)]
    return matches[0] if len(matches) == 1 else None


def _looks_like_sha(token: str) -> bool:
    # Real SHAs mix digits and letters; this keeps 7-digit numbers and
    # all-letter words like "defaced" from being linked as commits.
    return any(char.isdigit() for char in token) and any(char.isalpha() for char in token)


def _is_project_ticket(ticket_id: str, context: ArtifactLinkContext) -> bool:
    # Bare "XX-123" also matches things like UTF-8 or SHA-256, so only trust
    # keys that were ingested or carry the project's Jira key.
    if ticket_id in context.known_tickets:
        return True
    return bool(context.jira_project_key) and ticket_id.startswith(f"{context.jira_project_key}-")


def parse_citation_identifier(
    identifier: str, context: ArtifactLinkContext
) -> EvidenceTarget | None:
    """Best-effort target for a citation with no structured fields (reports
    generated before evidence_details existed, or instructor-typed ones)."""
    for match in _LINE_ANCHOR.finditer(identifier):
        raw_path = match.group("path")
        if "/" not in raw_path and "." not in raw_path:
            continue
        path = (
            _match_known_path(raw_path, context.known_paths)
            if context.known_paths is not None
            else raw_path
        )
        if not path:
            continue
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        return EvidenceTarget(
            type="file",
            file_path=path,
            line_start=min(start, end),
            line_end=max(start, end),
            commit_sha=match.group("sha"),
        )
    for ticket_id in _TICKET.findall(identifier):
        if _is_project_ticket(ticket_id, context):
            return EvidenceTarget(type="ticket", ticket_id=ticket_id)
    for token in _SHA.findall(identifier):
        if _looks_like_sha(token):
            return EvidenceTarget(type="commit", commit_sha=token.lower())
    if context.known_paths:
        for token in sorted(_PATH_TOKEN.findall(identifier), key=len, reverse=True):
            if ("/" in token or "." in token) and (
                path := _match_known_path(token, context.known_paths)
            ):
                return EvidenceTarget(type="file", file_path=path)
    return None


def evidence_target(detail: EvidenceDetail, context: ArtifactLinkContext) -> EvidenceTarget | None:
    if detail.file_path and detail.kind in {"file_lines", "diff_lines", "file"}:
        return EvidenceTarget(
            type="file",
            file_path=detail.file_path,
            line_start=detail.line_start,
            line_end=detail.line_end,
            commit_sha=detail.commit_sha,
        )
    if detail.kind == "commit" and detail.commit_sha:
        return EvidenceTarget(type="commit", commit_sha=detail.commit_sha)
    if detail.kind == "ticket":
        ticket_ids = _TICKET.findall(detail.identifier)
        return EvidenceTarget(
            type="ticket", ticket_id=ticket_ids[0] if ticket_ids else detail.identifier
        )
    return parse_citation_identifier(detail.identifier, context)


def build_evidence_link(
    citation: str, detail: EvidenceDetail, context: ArtifactLinkContext
) -> EvidenceLink:
    target = evidence_target(detail, context)
    viewer_path = external_url = external_source = None
    if target and target.type == "file":
        viewer_path = (
            file_viewer_path(context.project_id, target) if context.has_local_repository else None
        )
        external_url = file_url(context, target)
        external_source = context.repository_source if external_url else None
    elif target and target.type == "commit" and target.commit_sha:
        viewer_path = (
            commit_viewer_path(context.project_id, target.commit_sha)
            if context.has_local_repository
            else None
        )
        external_url = commit_url(context, target.commit_sha)
        external_source = context.repository_source if external_url else None
    elif target and target.type == "ticket" and target.ticket_id:
        if target.ticket_id in context.known_tickets:
            viewer_path = ticket_viewer_path(context.project_id, target.ticket_id)
        external_url = ticket_url(context, target.ticket_id)
        external_source = "jira" if external_url else None
    return EvidenceLink(
        citation=citation,
        identifier=detail.identifier,
        reason=detail.reason,
        kind=detail.kind,
        target=target,
        viewer_path=viewer_path,
        external_url=external_url,
        external_source=external_source,
    )


def _citation_details(
    citations: list[str], details: list[EvidenceDetail]
) -> list[tuple[str, EvidenceDetail]]:
    """Pair each display string with its structured detail. Matched by
    identifier rather than position, because an instructor edit can add or
    remove citation strings without touching evidence_details."""
    if not citations:
        return [
            (f"{d.identifier}{_CITATION_SEPARATOR}{d.reason}" if d.reason else d.identifier, d)
            for d in details
        ]
    by_identifier = {detail.identifier: detail for detail in details}
    pairs = []
    for citation in citations:
        identifier, _, reason = citation.partition(_CITATION_SEPARATOR)
        identifier = identifier.strip()
        detail = by_identifier.get(identifier) or EvidenceDetail(
            identifier=identifier, reason=reason.strip()
        )
        pairs.append((citation, detail))
    return pairs


# ── Context and report-level entry point ──────────────────────────────────


def project_repository_path(project: ProjectRecord) -> Path | None:
    try:
        return resolve_local_repository_path(project.local_repo_path)
    except ValueError:
        return None


def processed_jira_runs(
    project_id: str, jira_runs: JiraIngestionRunRepository
) -> list[JiraIngestionRunRecord]:
    """Runs with a cleaned snapshot, newest first."""
    runs = [run for run in jira_runs.list_project_runs(project_id) if run.cleaned_snapshot]
    return sorted(runs, key=lambda run: run.captured_at, reverse=True)


def build_link_context(
    project: ProjectRecord,
    jira_runs: JiraIngestionRunRepository | None = None,
    repository_path: Path | None = None,
) -> ArtifactLinkContext:
    url, source = repository_web_url(project.github_repo_url)
    head_sha = None
    if repository_path:
        # No usable saved URL: link to wherever the clone was taken from.
        if url is None:
            url, source = repository_web_url(remote_web_url(repository_remote_url(repository_path)))
        try:
            head_sha = resolve_commit(repository_path)
        except ArtifactNotFoundError:
            pass  # empty repository
    known_tickets = {
        ticket.ticket_id
        for run in (processed_jira_runs(project.id, jira_runs) if jira_runs else [])
        for ticket in run.cleaned_snapshot.tickets
    }
    return ArtifactLinkContext(
        project_id=project.id,
        repository_url=url,
        repository_source=source,
        jira_base_url=jira_base_url(project),
        jira_project_key=project.jira_project_key,
        has_local_repository=repository_path is not None,
        head_sha=head_sha,
        known_tickets=known_tickets,
    )


def _tracked_paths(project: ProjectRecord, repository_path: Path) -> set[str] | None:
    try:
        return list_tracked_paths(repository_path)
    except (ArtifactNotFoundError, subprocess.CalledProcessError):
        logger.warning(
            "Could not list files for project %s; plain-text file citations stay unlinked.",
            project.id,
        )
        return None


def build_report_evidence_links(
    report: AssessmentReport,
    project: ProjectRecord | None,
    jira_runs: JiraIngestionRunRepository | None = None,
) -> ReportEvidenceLinksResponse:
    if project is None:
        # Project deleted since grading: keep the citations, without links.
        context = ArtifactLinkContext(project_id=report.project_id)
    else:
        repository_path = project_repository_path(project)
        context = build_link_context(project, jira_runs, repository_path)
        if repository_path:
            context.known_paths = _tracked_paths(project, repository_path)
    dimensions = {
        dimension: [
            build_evidence_link(citation, detail, context)
            for citation, detail in _citation_details(
                score.evidence_citations, score.evidence_details
            )
        ]
        for dimension, score in report.rubric_scores.items()
    }
    return ReportEvidenceLinksResponse(
        report_id=report.report_id,
        course_id=report.course_id,
        project_id=report.project_id,
        sprint_id=report.sprint_id,
        dimensions=dimensions,
    )


# ── Viewer payloads ───────────────────────────────────────────────────────


def read_file_view(
    project: ProjectRecord,
    repository_path: Path,
    path: str,
    ref: str | None = None,
    start: int | None = None,
    end: int | None = None,
) -> ArtifactFileView:
    commit_sha, file_path, data = read_file_at_revision(repository_path, path, ref or "HEAD")
    context = build_link_context(project, repository_path=repository_path)
    is_binary = b"\0" in data[:8000]
    all_lines = [] if is_binary else data.decode("utf-8", errors="replace").splitlines()
    total = len(all_lines)

    highlight_start = highlight_end = None
    if start and total:
        low, high = sorted((start, end or start))
        highlight_start, highlight_end = min(low, total), min(high, total)

    first, last, truncated = (1, total, False) if total else (0, 0, False)
    if total > VIEWER_MAX_FILE_LINES:
        anchor_start = highlight_start or 1
        anchor_end = highlight_end or anchor_start
        first = max(1, anchor_start - VIEWER_CONTEXT_LINES)
        last = min(total, anchor_end + VIEWER_CONTEXT_LINES, first + VIEWER_MAX_FILE_LINES - 1)
        truncated = True

    target = EvidenceTarget(
        type="file",
        file_path=file_path,
        line_start=highlight_start,
        line_end=highlight_end,
        commit_sha=commit_sha,
    )
    external_url = file_url(context, target)
    return ArtifactFileView(
        project_id=project.id,
        file_path=file_path,
        commit_sha=commit_sha,
        total_lines=total,
        lines=[ArtifactFileLine(number=n, text=all_lines[n - 1]) for n in range(first, last + 1)]
        if total
        else [],
        first_line=first,
        last_line=last,
        highlight_start=highlight_start,
        highlight_end=highlight_end,
        is_binary=is_binary,
        truncated=truncated,
        external_url=external_url,
        external_source=context.repository_source if external_url else None,
    )


def read_commit_view(
    project: ProjectRecord, repository_path: Path, commit_sha: str
) -> ArtifactCommitView:
    commit = read_commit(
        repository_path,
        commit_sha,
        VIEWER_MAX_DIFF_CHARS_PER_FILE,
        VIEWER_MAX_DIFF_CHARS_PER_COMMIT,
    )
    context = build_link_context(project, repository_path=repository_path)
    external_url = commit_url(context, commit["commit_sha"])
    return ArtifactCommitView(
        project_id=project.id,
        **{
            **commit,
            "files_changed": [ArtifactCommitFile(**file) for file in commit["files_changed"]],
        },
        external_url=external_url,
        external_source=context.repository_source if external_url else None,
    )


def read_ticket_view(
    project: ProjectRecord,
    ticket_id: str,
    jira_runs: JiraIngestionRunRepository,
) -> ArtifactTicketView:
    """The ticket as captured by the most recent Jira sync that contains it."""
    for run in processed_jira_runs(project.id, jira_runs):
        for ticket in run.cleaned_snapshot.tickets:
            if ticket.ticket_id.upper() == ticket_id.upper():
                external_url = ticket_url(build_link_context(project), ticket.ticket_id)
                return ArtifactTicketView(
                    project_id=project.id,
                    ticket=ticket,
                    captured_at=run.captured_at,
                    sprint_id=run.sprint_id,
                    external_url=external_url,
                    external_source="jira" if external_url else None,
                )
    raise ArtifactNotFoundError(
        f"Jira ticket {ticket_id} was not found in any synced snapshot for this project."
    )
