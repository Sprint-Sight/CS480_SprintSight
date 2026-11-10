"""What the grounding judge gets to read.

The judge used to receive the whole bundle as JSON. For a real sprint that is every commit's
full diff, every repository file's contents and the uploaded context documents: one real run
measured ~708,000 tokens against a 49,152-token context, so the judge failed on every real
assessment and only ever worked on the small fixtures.

The judge only has to check the claims it is given, and code has already removed every claim
whose identifier does not exist in the bundle. So it needs the records the claims CITE, and only
enough of the rest to check statements about the team as a whole.

What a citation brings in:
  * a commit SHA        -> that commit in full, with its diffs;
  * a file path         -> that file's contents at HEAD (from the repository snapshot). Only when
                           the snapshot lacks the file are the diffs of the commits touching it
                           shown instead. A file is never a reason to show every commit that
                           touched it: a claim about `src/app.py:L10-L24` is about the file at HEAD;
  * a Jira ticket       -> tickets are always listed (they are small).

Everything uncited is shown in a form that shrinks until the prompt fits. `build_judge_bundle(...,
level=n)` is that ladder and `fit_judge_bundle` walks it:

  0  every commit with its file list, every file listed
  1  uncited commits lose their per-file lists
  2  uncited commits shrink to sha, author, short message, date and line counts; only cited files
     are listed (with the file total)
  3  uncited commits are replaced by per-author totals
  4  cited commits show diffs only for the files the claims mention (else their three largest
     changes), and cited files show only the lines the claims cite plus context

Cited evidence is never cut off mid-way: truncated evidence makes a judge call a true claim
fabricated. If even level 4 does not fit, the caller gets the per-section sizes and fails loudly.

Not included at any level: uploaded project-context documents (background for the grader, never
evidence) and the instructor's expectations.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from schemas.artifact_bundle import ArtifactBundle

_HEX_TOKEN = re.compile(r"[0-9a-f]{7,40}")
_LINE_RANGE = re.compile(r"([\w./-]+\.\w+):L(\d+)(?:-L?(\d+))?")

MAX_LEVEL = 4
_SHORT_MESSAGE_CHARS = 100
_LARGEST_CHANGES_KEPT = 3
_EXCERPT_CONTEXT_LINES = 10

_NOTE = (
    "To fit the context window, commits and files that no claim mentions are shown in reduced form "
    "or only as totals{narrowed}. Their absence is not evidence against any claim."
)
_NARROWED = (
    ", and for cited commits only the files the claims mention (else the largest changes) have diffs, "
    "while cited files show only the cited lines with context"
)


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _mentions_path(path: str, claims: str) -> bool:
    path = _posix(path)
    return path in claims or PurePosixPath(path).name in claims


def _cited_line_ranges(claims: str) -> dict[str, list[tuple[int, int]]]:
    """{path as written in the claim: [(first line, last line), ...]} from `path:L10-L24` anchors."""
    ranges: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for path, start, end in _LINE_RANGE.findall(claims):
        first = int(start)
        ranges[path].append((first, int(end) if end else first))
    return ranges


def _excerpts(content: str, spans: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """The cited line ranges of `content` with a little context, overlapping ranges merged."""
    lines = content.splitlines()
    windows: list[list[int]] = []
    for first, last in sorted(spans):
        low, high = max(1, first - _EXCERPT_CONTEXT_LINES), min(len(lines), last + _EXCERPT_CONTEXT_LINES)
        if windows and low <= windows[-1][1] + 1:
            windows[-1][1] = max(windows[-1][1], high)
        else:
            windows.append([low, high])
    return [{"from": low, "to": high, "text": "\n".join(lines[low - 1:high])} for low, high in windows if low <= high]


def build_judge_bundle(bundle: ArtifactBundle, claims_text: str, level: int = 0) -> dict[str, Any]:
    """The bundle reduced to what is needed to check `claims_text`, at reduction `level` (see
    the module docstring)."""
    claims = _posix(claims_text)
    claimed_shas = set(_HEX_TOKEN.findall(claims.lower()))
    narrow = level >= MAX_LEVEL
    ranges = _cited_line_ranges(claims) if narrow else {}

    snapshot_with_content = {
        _posix(file.path)
        for file in (bundle.repo_snapshot.files if bundle.repo_snapshot else [])
        if file.content
    }

    def commit_cited(sha: str) -> bool:
        return any(sha.lower().startswith(token) for token in claimed_shas)

    def diff_wanted(commit_is_cited: bool, filename: str) -> bool:
        # A file alone brings in a diff only if the snapshot cannot show the file itself.
        return commit_is_cited or (_mentions_path(filename, claims) and _posix(filename) not in snapshot_with_content)

    commits: list[dict[str, Any]] = []
    per_author: dict[str, dict[str, int]] = defaultdict(lambda: {"commits": 0, "lines_added": 0, "lines_deleted": 0})
    for commit in bundle.commits:
        cited = commit_cited(commit.sha)
        if level >= 3 and not cited:
            totals = per_author[commit.author]
            totals["commits"] += 1
            totals["lines_added"] += commit.lines_added
            totals["lines_deleted"] += commit.lines_deleted
            continue
        if level >= 2 and not cited:
            commits.append({
                "sha": commit.sha[:12],
                "author": commit.author,
                "message": commit.message if len(commit.message) <= _SHORT_MESSAGE_CHARS else commit.message[:_SHORT_MESSAGE_CHARS] + "...",
                "date": commit.timestamp.date().isoformat(),
                "lines_added": commit.lines_added,
                "lines_deleted": commit.lines_deleted,
            })
            continue

        with_diffs = [f for f in commit.files_changed if f.diff and diff_wanted(cited, f.filename)]
        if narrow and cited and with_diffs:
            mentioned = [f for f in with_diffs if _mentions_path(f.filename, claims)]
            largest = sorted(with_diffs, key=lambda f: f.lines_added + f.lines_deleted, reverse=True)[:_LARGEST_CHANGES_KEPT]
            with_diffs = mentioned or largest
        diff_names = {f.filename for f in with_diffs}

        files = []
        for changed in commit.files_changed:
            if level >= 1 and not cited and not _mentions_path(changed.filename, claims):
                continue
            entry: dict[str, Any] = {
                "filename": changed.filename,
                "change_type": changed.change_type,
                "lines_added": changed.lines_added,
                "lines_deleted": changed.lines_deleted,
            }
            if changed.diff and changed.filename in diff_names:
                entry["diff"] = changed.diff
            files.append(entry)
        record: dict[str, Any] = {
            "sha": commit.sha,
            "author": commit.author,
            "message": commit.message,
            "timestamp": commit.timestamp.isoformat(),
            "lines_added": commit.lines_added,
            "lines_deleted": commit.lines_deleted,
            "files_changed": files,
        }
        if level >= 1 and len(files) != len(commit.files_changed):
            record["files_total"] = len(commit.files_changed)
        commits.append(record)

    snapshot: dict[str, Any] | None = None
    if bundle.repo_snapshot is not None:
        listed = []
        for file in bundle.repo_snapshot.files:
            file_cited = _mentions_path(file.path, claims)
            if level >= 2 and not file_cited:
                continue
            entry = {"path": file.path, "size_bytes": file.size_bytes, "line_count": file.line_count}
            if file.content and file_cited:
                spans = [span for path, found in ranges.items() if _posix(file.path).endswith(_posix(path)) for span in found]
                if narrow and spans:
                    entry["excerpts"] = _excerpts(file.content, spans)
                else:
                    entry["content"] = file.content
            listed.append(entry)
        snapshot = {"head_sha": bundle.repo_snapshot.head_sha, "files": listed}
        if level >= 2:
            snapshot["files_total"] = len(bundle.repo_snapshot.files)

    judged: dict[str, Any] = {
        "team_id": bundle.team_id,
        "sprint_id": bundle.sprint_id,
        "commits": commits,
        "jira_tickets": [ticket.model_dump(mode="json") for ticket in bundle.jira_tickets],
        "peer_evaluations": [evaluation.model_dump(mode="json") for evaluation in bundle.peer_evaluations],
        "collaboration_metrics": bundle.collaboration_metrics,
        "artifact_metrics": bundle.artifact_metrics,
        "repo_snapshot": snapshot,
    }
    if level >= 3:
        judged["other_commits_by_author"] = dict(per_author)
        judged["commits_total"] = len(bundle.commits)
    if level >= 1:
        judged["note"] = _NOTE.format(narrowed=_NARROWED if narrow else "")
    return judged


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), default=str)


def judge_bundle_json(bundle: ArtifactBundle, claims_text: str, level: int = 0) -> str:
    """Compact JSON of `build_judge_bundle`, as sent to the judge."""
    return _dump(build_judge_bundle(bundle, claims_text, level))


def section_sizes(data: dict[str, Any]) -> dict[str, int]:
    """Characters per top-level section, for explaining a bundle that is still too big."""
    return {key: len(_dump({key: value})) for key, value in data.items()}


def fit_judge_bundle(bundle: ArtifactBundle, claims_text: str, max_chars: int) -> tuple[str, int, dict[str, int]]:
    """The least-reduced view of the bundle that fits in `max_chars`.

    Returns (json, level, section_sizes). If even the most reduced view is over the limit it is
    returned anyway, so the caller can report the sizes instead of guessing what is large."""
    for level in range(MAX_LEVEL + 1):
        data = build_judge_bundle(bundle, claims_text, level)
        text = _dump(data)
        if len(text) <= max_chars or level == MAX_LEVEL:
            return text, level, section_sizes(data)
    raise AssertionError("unreachable")
