import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydriller import Repository

from app.repositories.in_memory import metrics_repo
from app.repositories.interfaces import IngestionMetricBundle, MetricsRepository, ProjectRepository, UserRepository
from app.schemas.auth import Role
from app.schemas.assessment import CommitInfo, FileDiff, IngestionRequest

# Diff caps keep one huge commit (e.g. an initial scaffold) from bloating the
# ingestion_commits rows and the AI payload. The AI engine budgets what it
# actually shows the model; these only bound what is stored.
DIFF_MAX_CHARS_PER_FILE = int(os.getenv("GIT_DIFF_MAX_CHARS_PER_FILE", "4000"))
DIFF_MAX_CHARS_PER_COMMIT = int(os.getenv("GIT_DIFF_MAX_CHARS_PER_COMMIT", "16000"))

# Caps for the snapshot of the repository at its latest commit, which lets the
# AI engine grade the final submission rather than only the commit history.
SNAPSHOT_MAX_FILE_BYTES = int(os.getenv("REPO_SNAPSHOT_MAX_FILE_BYTES", "100000"))
SNAPSHOT_MAX_TOTAL_BYTES = int(os.getenv("REPO_SNAPSHOT_MAX_TOTAL_BYTES", "4000000"))

# Kept in step with ai-engine/services/llm_client.py's noise lists.
_NOISE_PATH_SEGMENTS = (
    "node_modules/", "vendor/", "venv/", ".venv/", "env/", "dist/", "build/",
    "out/", "__pycache__/", ".next/", ".nuxt/", "target/", "bower_components/",
    ".gradle/", ".m2/", "pods/", "deriveddata/", ".terraform/", ".angular/",
    ".cache/", ".idea/", ".vscode/", "coverage/",
)
_LOCKFILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "pipfile.lock", "cargo.lock", "go.sum", "composer.lock",
    "gemfile.lock", "shrinkwrap.yaml", "bun.lockb",
}
_GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", ".chunk.js", ".bundle.js")


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


def _is_noise_path(path: str) -> bool:
    """Vendored, generated, or lock files: their diffs/contents say nothing
    about the team's own engineering and would only burn the LLM's context."""
    lower = path.lower().replace("\\", "/")
    padded = f"/{lower}"
    if any(f"/{segment}" in padded for segment in _NOISE_PATH_SEGMENTS):
        return True
    basename = lower.rsplit("/", 1)[-1]
    return basename in _LOCKFILE_NAMES or basename.endswith(_GENERATED_SUFFIXES)


def _cap_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Cut text at the last whole line within max_chars."""
    if len(text) <= max_chars:
        return text, False
    cut = text.rfind("\n", 0, max_chars)
    return text[: cut if cut > 0 else max_chars], True


def _file_diff_text(
    path: str, diff: str | None, remaining_commit_chars: int,
) -> tuple[str | None, bool]:
    """Returns (diff text or None, whether real diff text was cut or dropped)."""
    if not diff or _is_noise_path(path):
        return None, False
    if remaining_commit_chars <= 0:
        return None, True
    return _cap_text(diff, min(DIFF_MAX_CHARS_PER_FILE, remaining_commit_chars))


def _extract_commits_from_repository(repository_path: Path) -> list[CommitInfo]:
    commits: list[CommitInfo] = []
    for commit in Repository(str(repository_path)).traverse_commits():
        files_changed = []
        remaining_commit_chars = DIFF_MAX_CHARS_PER_COMMIT
        for mod in commit.modified_files:
            # pydriller uses the OS separator; Git (and the snapshot) use "/".
            filename = (mod.new_path or mod.old_path or "").replace("\\", "/")
            diff, diff_truncated = _file_diff_text(filename, mod.diff, remaining_commit_chars)
            remaining_commit_chars -= len(diff or "")
            files_changed.append(FileDiff(
                filename=filename,
                change_type=_change_type(mod.change_type.name),
                lines_added=max(mod.added_lines or 0, 0),
                lines_deleted=max(mod.deleted_lines or 0, 0),
                diff=diff,
                diff_truncated=diff_truncated,
            ))
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


def collect_repository_snapshot(repository_path: Path, revision: str = "HEAD") -> dict:
    """Read every tracked, non-noise file at `revision` straight from the Git
    object store (no checkout, so the working tree is never touched).

    Returns a JSON-ready dict for the AI payload's `repo_snapshot`. Binary or
    oversized files are listed with `content: None` so the tree stays complete
    while the payload stays bounded by SNAPSHOT_MAX_TOTAL_BYTES.
    """
    head_sha = _git_output(repository_path, "rev-parse", revision).strip()
    listing = _git_output(repository_path, "ls-tree", "-r", "-l", "--full-tree", head_sha)
    entries: list[tuple[str, str, int]] = []
    omitted = 0
    for line in listing.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) != 4 or parts[1] != "blob" or not parts[3].isdigit():
            continue  # submodules, symlinks to trees, etc.
        if _is_noise_path(path):
            omitted += 1
            continue
        entries.append((path, parts[2], int(parts[3])))

    wanted = [(path, oid) for path, oid, size in entries if size <= SNAPSHOT_MAX_FILE_BYTES]
    blobs = _read_blobs(repository_path, [oid for _, oid in wanted])

    files: list[dict] = []
    total = 0
    truncated = False
    for path, oid, size in sorted(entries):
        content: str | None = None
        data = blobs.get(oid)
        if data is not None and b"\0" not in data[:8000]:
            if total + len(data) <= SNAPSHOT_MAX_TOTAL_BYTES:
                content = data.decode("utf-8", errors="replace")
                total += len(data)
            else:
                truncated = True
        files.append({
            "path": path,
            "size_bytes": size,
            "line_count": _line_count(content) if content is not None else None,
            "content": content,
        })
    return {
        "head_sha": head_sha,
        "files": files,
        "truncated": truncated,
        "omitted_noise_files": omitted,
    }


def _line_count(text: str) -> int:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def _git_output(repository_path: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository_path), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def _read_blobs(repository_path: Path, object_ids: list[str]) -> dict[str, bytes]:
    """Fetch many blobs in one `git cat-file --batch` process."""
    if not object_ids:
        return {}
    output = subprocess.run(
        ["git", "-C", str(repository_path), "cat-file", "--batch"],
        input="\n".join(object_ids).encode() + b"\n",
        check=True,
        capture_output=True,
    ).stdout
    blobs: dict[str, bytes] = {}
    position = 0
    while position < len(output):
        header_end = output.index(b"\n", position)
        header = output[position:header_end].split()
        position = header_end + 1
        if len(header) != 3:
            continue  # "<oid> missing"
        size = int(header[2])
        blobs[header[0].decode()] = output[position:position + size]
        position += size + 1
    return blobs


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
