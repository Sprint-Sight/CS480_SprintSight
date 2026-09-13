import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydriller import Repository

from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import IngestionMetricBundle, MetricsRepository, ProjectRepository, UserRepository
from app.schemas.auth import Role
from app.schemas.assessment import CommitInfo, FileDiff, IngestionRequest


def extract_local_commits(repository_path: Path) -> list[CommitInfo]:
    with tempfile.TemporaryDirectory(prefix="sprintsight-git-") as temporary_dir:
        writable_repository = Path(temporary_dir) / repository_path.name
        subprocess.run(
            ["git", "clone", "--no-local", "--quiet", str(repository_path), str(writable_repository)],
            check=True,
            capture_output=True,
            text=True,
        )
        return _extract_commits_from_repository(writable_repository)


def _extract_commits_from_repository(repository_path: Path) -> list[CommitInfo]:
    commits: list[CommitInfo] = []
    for commit in Repository(str(repository_path)).traverse_commits():
        files_changed = [
            FileDiff(
                filename=mod.new_path or mod.old_path or "",
                change_type=_change_type(mod.change_type.name),
                lines_added=max(mod.added_lines or 0, 0),
                lines_deleted=max(mod.deleted_lines or 0, 0),
            )
            for mod in commit.modified_files
        ]
        commits.append(CommitInfo(
            sha=commit.hash,
            author=commit.author.name or commit.author.email,
            author_email=_normalize_email(commit.author.email),
            message=commit.msg,
            timestamp=_as_utc(commit.author_date),
            lines_added=sum(file.lines_added for file in files_changed),
            lines_deleted=sum(file.lines_deleted for file in files_changed),
            files_changed=files_changed,
        ))
    return commits


def _normalize_email(email: str | None) -> str | None:
    normalized = email.strip().casefold() if email else ""
    return normalized or None


def _link_commit_authors_to_students(
    commits: list[CommitInfo],
    project_id: str,
    projects: ProjectRepository,
    users: UserRepository,
) -> None:
    member_ids = set(projects.list_member_ids(project_id))
    resolved_by_email: dict[str, str | None] = {}
    for commit in commits:
        normalized_email = _normalize_email(commit.author_email)
        if not normalized_email:
            continue
        commit.author_email = normalized_email
        if normalized_email not in resolved_by_email:
            user = users.get_by_email(normalized_email)
            resolved_by_email[normalized_email] = (
                user.id
                if user and user.is_active and user.role == Role.STUDENT and user.id in member_ids
                else None
            )
        commit.student_id = resolved_by_email[normalized_email]


def resolve_local_repository_path(local_repo_path: str | None) -> Path | None:
    if not local_repo_path:
        return None
    from app.core.config import get_settings

    root = get_settings().local_repository_root.expanduser().resolve()
    candidate = (root / local_repo_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Local repository path must remain inside the configured repository root.")
    if not candidate.is_dir() or not (candidate / ".git").exists():
        raise ValueError("Configured local repository does not exist or is not a Git repository.")
    return candidate


def ingest_github_metrics(
    payload: IngestionRequest,
    repository_path: Path | None = None,
    metrics_repository: MetricsRepository | None = None,
    projects: ProjectRepository | None = None,
    users: UserRepository | None = None,
) -> IngestionMetricBundle:
    commits = extract_local_commits(repository_path) if repository_path else []
    if projects and users:
        _link_commit_authors_to_students(commits, payload.project_id, projects, users)
    metrics = IngestionMetricBundle(
        course_id=payload.course_id,
        project_id=payload.project_id,
        sprint_id=payload.sprint_id,
        commit_frequency=float(len(commits)),
        code_churn=sum(commit.lines_added + commit.lines_deleted for commit in commits),
        pr_turnaround_hours=None,
        assigned_story_points=None,
        completion_percent=None,
        commits=commits,
        local_repo_path=str(repository_path) if repository_path else None,
        head_sha=_repository_head(repository_path) if repository_path else None,
        captured_at=datetime.now(timezone.utc),
    )
    (metrics_repository or metrics_repo).save_metrics(metrics)
    return metrics


def _change_type(change_type: str) -> str:
    return {
        "ADD": "added",
        "MODIFY": "modified",
        "DELETE": "deleted",
        "RENAME": "renamed",
    }.get(change_type, "modified")


def _repository_head(repository_path: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repository_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
