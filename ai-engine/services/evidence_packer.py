"""
services/evidence_packer.py

Builds the "Student Artifacts" block for ONE rubric dimension under a token
budget, and records every citable anchor it showed the model so the
citations can be verified afterwards (services/grounding.py's
resolve_citations).

Why this replaced the fixed 30-commit sample:
  - The old path pretty-printed up to 30 commits as indented JSON. Real
    sprints have 200-550 commits, so the model saw 5-15% of the history, and
    indented JSON spends most of its tokens on keys and whitespace.
  - It only showed +/- line counts, so "code quality" was judged from commit
    messages, never from code.
  - Citations could only point at a commit, never at the lines that justify
    the score.

What the model sees now, in priority order, each section only taking what
the budget leaves:
  1. Small fixed inputs (instructor expectations, Jira tickets, metrics),
     one compact line per record.
  2. A commit LEDGER: one line per commit for the WHOLE history, so the
     model can reason about the entire project, not a sample.
  3. The repository FILE TREE at the submitted HEAD (every file + line count).
  4. Line-numbered CONTENTS of the files at HEAD most relevant to this
     dimension (tests for `testing`, READMEs/docs for `documentation`, ...).
  5. Line-numbered DIFF excerpts from relevant commits, spread round-robin
     across authors so one member's work does not crowd out the rest.
Every file/diff block carries a ready-made citation anchor
(`path:L<start>-L<end>` or `path:L<start>-L<end>@<sha7>`), which the model
copies instead of inventing locations.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any

# Calibrated against ai-engine/audit_logs: Ollama's reported prompt_tokens
# for our prompts came out at 2.7-3.5 chars/token (JSON- and code-heavy text
# tokenizes densely), so the old `chars // 4` undercounted by up to ~45%.
# 3.0 errs on the side of over-estimating, which only costs a little unused
# context, whereas under-estimating gets the prompt silently truncated.
CHARS_PER_TOKEN = float(os.getenv("LLM_CHARS_PER_TOKEN", "3.0"))
# Lines shown per file at HEAD. Code is token-dense (~13 tokens per numbered
# line), so source files get a shorter slice: seeing the opening of many
# files says more about a whole project than all of a few. Docs and CI
# configs are short and read top to bottom, so they get more.
_FILE_LINE_CAPS = {"source": 120, "test": 150, "docs": 250, "cicd": 200}
if os.getenv("LLM_EVIDENCE_MAX_FILE_LINES"):
    _FILE_LINE_CAPS = dict.fromkeys(_FILE_LINE_CAPS, int(os.environ["LLM_EVIDENCE_MAX_FILE_LINES"]))
MAX_DIFF_LINES = int(os.getenv("LLM_EVIDENCE_MAX_DIFF_LINES", "60"))
_MAX_LINE_CHARS = 240        # minified/generated lines carry no signal past this
_MIN_FILE_SLICE_LINES = 25   # below this a partial file is not worth its header
_MIN_DIFF_SLICE_LINES = 12
_COVERAGE_NOTE_TOKENS = 200  # written last, so its room is set aside up front

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


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def is_noise_path(path: str) -> bool:
    """Vendored, generated, or lock files.

    Matches whole path segments: a plain substring test would treat
    `src/layout/Header.tsx` as noise because it contains "out/".
    """
    lower = path.lower().replace("\\", "/")
    padded = f"/{lower}"
    if any(f"/{segment}" in padded for segment in _NOISE_PATH_SEGMENTS):
        return True
    basename = lower.rsplit("/", 1)[-1]
    return basename in _LOCKFILE_NAMES or basename.endswith(_GENERATED_SUFFIXES)


# ── File categories ────────────────────────────────────────────────────────

_TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|specs?|e2e|cypress)/"
    r"|(^|/)test_[^/]+$|_test\.\w+$|\.(test|spec)\.\w+$"
    r"|(^|/)(conftest\.py|pytest\.ini|karma\.conf\.js)$"
    r"|(^|/)(jest|vitest|playwright)\.config\.\w+$"
)
_TEST_CAMEL_RE = re.compile(r"[a-z0-9]Tests?\.(java|kt|cs|swift|scala)$")
_CICD_RE = re.compile(
    r"(^|/)\.github/workflows/|(^|/)\.gitlab-ci\.ya?ml$|(^|/)jenkinsfile$"
    r"|(^|/)\.circleci/|(^|/)(azure|bitbucket)-pipelines"
    r"|(^|/)dockerfile[^/]*$|\.dockerfile$|(^|/)(docker-)?compose[^/]*\.ya?ml$"
    r"|(^|/)makefile$|\.tf$|(^|/)(k8s|helm|kubernetes)/|(^|/)procfile$"
    r"|(^|/)\.pre-commit-config\.ya?ml$|(^|/)sonar-project\.properties$"
    r"|(^|/)\.github/dependabot\.ya?ml$"
)
_DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".adoc"}
_DOC_NAMES = {
    "changelog", "contributing", "openapi.yaml", "openapi.yml", "openapi.json",
    "swagger.yaml", "swagger.yml", "swagger.json",
}
_PRIMARY_CODE = {
    ".py", ".java", ".kt", ".kts", ".scala", ".go", ".rs", ".rb", ".php", ".cs",
    ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".swift", ".m", ".js", ".jsx",
    ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".dart",
}
_SECONDARY_CODE = {".sql", ".sh", ".html", ".css", ".scss", ".less"}


def file_category(path: str) -> str | None:
    """One of "test", "cicd", "docs", "source", or None (assets, data, ...)."""
    lower = path.lower()
    if _TEST_RE.search(lower) or _TEST_CAMEL_RE.search(path):
        return "test"
    if _CICD_RE.search(lower):
        return "cicd"
    posix = PurePosixPath(lower)
    if (
        posix.suffix in _DOC_EXTENSIONS
        or posix.name.startswith("readme")
        or posix.stem in _DOC_NAMES
        or posix.name in _DOC_NAMES
        or (posix.suffix == ".txt" and re.search(r"(^|/)docs?/", lower))
    ):
        return "docs"
    if posix.suffix in _PRIMARY_CODE or posix.suffix in _SECONDARY_CODE:
        return "source"
    return None


def _code_weight(path: str) -> float:
    return 1.0 if PurePosixPath(path.lower()).suffix in _PRIMARY_CODE else 0.35


# ── Dimension plans ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _DimensionPlan:
    # File category whose HEAD contents and diffs are shown; None = none.
    category: str | None
    # Max share of the post-fixed-inputs budget the commit ledger may use.
    ledger_share: float
    # Share of what is left after the ledger and tree that goes to HEAD file
    # contents first (diffs get the rest, then HEAD takes any leftover).
    head_share: float


_PLANS: dict[str, _DimensionPlan] = {
    # File-based dimensions cap the ledger at 30%: the computed facts already
    # cover every commit, and the collaboration dimension sees the full
    # ledger, so the rest of the budget goes to actual code.
    "code_quality": _DimensionPlan("source", 0.30, 0.45),
    "testing": _DimensionPlan("test", 0.30, 0.60),
    "documentation": _DimensionPlan("docs", 0.30, 0.70),
    "cicd": _DimensionPlan("cicd", 0.30, 0.70),
    # Collaboration is about who did what and when: the ledger is the
    # evidence, file contents are not.
    "collaboration": _DimensionPlan(None, 0.90, 0.0),
    "requirements": _DimensionPlan(None, 0.0, 0.0),
}


# ── Index of what the model was shown (for citation verification) ─────────

Range = tuple[int, int]


@dataclass
class EvidenceIndex:
    head_sha: str | None = None
    commit_shas: list[str] = field(default_factory=list)
    # path -> line ranges shown from the file at HEAD
    head_lines: dict[str, list[Range]] = field(default_factory=dict)
    # (path, full sha) -> new-file line ranges shown in that commit's diff
    diff_lines: dict[tuple[str, str], list[Range]] = field(default_factory=dict)
    known_paths: set[str] = field(default_factory=set)
    tickets: set[str] = field(default_factory=set)
    # JSON of the non-commit inputs, for verifying metric-style citations.
    other_values_json: str = "{}"
    # Flat metric name -> value, from the dict-valued inputs shown
    # (collaboration_metrics, artifact_metrics).
    metrics: dict[str, Any] = field(default_factory=dict)

    def find_commit(self, sha_prefix: str) -> str | None:
        prefix = sha_prefix.lower()
        matches = [sha for sha in self.commit_shas if sha.lower().startswith(prefix)]
        return matches[0] if len(matches) == 1 else None


@dataclass
class PackStats:
    budget_tokens: int
    used_tokens: int = 0
    commits_total: int = 0
    commits_listed: int = 0
    ledger_format: str = "none"
    tree_files: int = 0
    head_candidates: int = 0
    head_files_shown: int = 0
    head_lines_shown: int = 0
    outline_files: int = 0
    diff_candidates: int = 0
    diff_excerpts: int = 0
    diff_commits: int = 0
    diff_authors: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PackedEvidence:
    text: str
    index: EvidenceIndex
    stats: PackStats


# ── Rendering helpers ──────────────────────────────────────────────────────

def _first_line(message: str, limit: int) -> str:
    line = (message or "").strip().splitlines()[0] if (message or "").strip() else "(no message)"
    line = line.replace("|", "/")
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _clip(line: str) -> str:
    line = line.rstrip()
    return line if len(line) <= _MAX_LINE_CHARS else line[:_MAX_LINE_CHARS] + " …"


def _merge_ranges(numbers: Iterable[int]) -> list[Range]:
    ranges: list[Range] = []
    for number in sorted(set(numbers)):
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], number)
        else:
            ranges.append((number, number))
    return ranges


def _anchor(path: str, start: int, end: int, sha: str | None = None) -> str:
    lines = f"L{start}" if start == end else f"L{start}-L{end}"
    return f"{path}:{lines}" + (f"@{sha[:7]}" if sha else "")


def _relevant_files(commit: dict, category: str | None) -> list[dict]:
    files = [f for f in commit.get("files_changed") or [] if not is_noise_path(f.get("filename", ""))]
    if category is None:
        return files
    return [f for f in files if file_category(f["filename"]) == category]


def _normalise_paths(commit: dict) -> dict:
    """Commits ingested on Windows carry backslash paths; Git, the snapshot,
    and citations all use "/"."""
    files = [
        {**f, "filename": str(f.get("filename", "")).replace("\\", "/")}
        for f in commit.get("files_changed") or []
    ]
    return {**commit, "files_changed": files}


# ── Sections ───────────────────────────────────────────────────────────────

def _render_fixed_inputs(bundle: dict, fields: tuple[str, ...], index: EvidenceIndex) -> str:
    parts = [
        f"team_id: {bundle.get('team_id')}",
        f"sprint_id: {bundle.get('sprint_id')}",
        f"instructor_expectations: {bundle.get('instructor_expectations')}",
    ]
    other_values: dict[str, Any] = {}
    for name in fields:
        if name == "commits":
            continue
        value = bundle.get(name)
        other_values[name] = value
        if isinstance(value, dict):
            index.metrics.update({k: v for k, v in value.items() if v is not None})
        if name == "jira_tickets":
            tickets = value or []
            index.tickets.update(str(t.get("ticket_id")) for t in tickets if t.get("ticket_id"))
            parts.append(f"\nJIRA TICKETS ({len(tickets)}), one JSON object per line:")
            parts.extend(json.dumps(t, ensure_ascii=True, sort_keys=True) for t in tickets)
            if not tickets:
                parts.append("(none)")
        else:
            parts.append(f"\n{name}: {json.dumps(value, ensure_ascii=True, sort_keys=True)}")
    index.other_values_json = json.dumps(other_values, ensure_ascii=True, default=str)
    return "\n".join(parts)


def _ledger_line(commit: dict, category: str | None, detailed: bool) -> str:
    timestamp = str(commit.get("timestamp") or "")
    added, deleted = commit.get("lines_added", 0), commit.get("lines_deleted", 0)
    if not detailed:
        return (
            f"{commit['sha'][:7]} | {timestamp[:10]} | {commit.get('author')} | "
            f"+{added}/-{deleted} | {_first_line(commit.get('message', ''), 60)}"
        )
    files = _relevant_files(commit, None)
    preferred = [f for f in files if category and file_category(f["filename"]) == category]
    shown = (preferred + [f for f in files if f not in preferred])[:3]
    extra = len(files) - len(shown)
    file_text = ", ".join(f["filename"] for f in shown) + (f" +{extra} more" if extra > 0 else "")
    return (
        f"{commit['sha'][:7]} | {timestamp[:10]} | {commit.get('author')} | "
        f"+{added}/-{deleted} | {_first_line(commit.get('message', ''), 100)} | {file_text or '-'}"
    )


def _render_ledger(
    commits: list[dict], category: str | None, budget: int, index: EvidenceIndex, stats: PackStats,
) -> str:
    """Every commit, one line each. Falls back to a shorter line format, then
    to the most relevant subset, only when the whole history cannot fit."""
    stats.commits_total = len(commits)
    if not commits:
        return ""
    header_all = (
        f"COMMIT LEDGER: all {len(commits)} commits, oldest first.\n"
        "Columns: sha | date | author | +added/-deleted | message{files}"
    )
    for detailed, label in ((True, "detailed"), (False, "compact")):
        lines = [_ledger_line(c, category, detailed) for c in commits]
        text = header_all.format(files=" | files" if detailed else "") + "\n" + "\n".join(lines)
        if estimate_tokens(text) <= budget:
            stats.ledger_format = label
            stats.commits_listed = len(commits)
            index.commit_shas.extend(c["sha"] for c in commits)
            return text

    # Still too long: keep the commits that matter most for this dimension.
    def relevance(commit: dict) -> tuple[int, int]:
        touches = 1 if category is None or _relevant_files(commit, category) else 0
        return touches, commit.get("lines_added", 0) + commit.get("lines_deleted", 0)

    header_cost = estimate_tokens(header_all) + 40
    chosen: set[str] = set()
    used = header_cost
    for commit in sorted(commits, key=relevance, reverse=True):
        cost = estimate_tokens(_ledger_line(commit, category, False)) + 1
        if used + cost > budget:
            continue
        chosen.add(commit["sha"])
        used += cost
    kept = [c for c in commits if c["sha"] in chosen]
    stats.ledger_format = "compact-subset"
    stats.commits_listed = len(kept)
    index.commit_shas.extend(c["sha"] for c in kept)
    header = (
        f"COMMIT LEDGER: {len(kept)} of {len(commits)} commits (the most relevant to this "
        f"dimension), oldest first. The other {len(commits) - len(kept)} are still counted "
        "in the computed facts.\nColumns: sha | date | author | +added/-deleted | message"
    )
    return header + "\n" + "\n".join(_ledger_line(c, category, False) for c in kept)


def _render_tree(snapshot: dict, budget: int, index: EvidenceIndex, stats: PackStats) -> str:
    files = snapshot.get("files") or []
    index.known_paths.update(f["path"] for f in files)
    stats.tree_files = len(files)
    by_dir: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        directory, _, _ = f["path"].rpartition("/")
        by_dir[directory].append(f)
    head = (snapshot.get("head_sha") or "")[:7]
    header = (
        f"REPOSITORY FILE TREE at the submitted HEAD {head} ({len(files)} files; "
        "line counts in parentheses). Files whose contents are not shown below still exist."
    )
    lines = []
    for directory in sorted(by_dir):
        entries = ", ".join(
            f"{PurePosixPath(f['path']).name} ({f['line_count'] if f.get('line_count') is not None else 'binary'})"
            for f in sorted(by_dir[directory], key=lambda f: f["path"])
        )
        lines.append(f"{directory or '.'}/: {entries}")
    text = header + "\n" + "\n".join(lines)
    if estimate_tokens(text) <= budget:
        return text
    # Too many files to list individually: summarise per directory.
    summary = []
    for directory in sorted(by_dir):
        dir_files = by_dir[directory]
        total_lines = sum(f.get("line_count") or 0 for f in dir_files)
        summary.append(f"{directory or '.'}/: {len(dir_files)} files, {total_lines} lines")
    return header.replace("line counts in parentheses", "summarised per directory") + "\n" + "\n".join(summary)


def _rank_head_files(snapshot: dict, category: str, churn: Counter[str]) -> list[dict]:
    candidates = [
        f for f in snapshot.get("files") or []
        if f.get("content") and file_category(f["path"]) == category
    ]
    if category == "docs":
        def doc_key(f: dict) -> tuple[int, int]:
            path = f["path"].lower()
            name = PurePosixPath(path).name
            tier = 0 if name.startswith("readme") and "/" not in path else 1 if name.startswith("readme") else 2
            return tier, -(f.get("line_count") or 0)
        return sorted(candidates, key=doc_key)

    def score(f: dict) -> float:
        lines = f.get("line_count") or 0
        return (1 + churn[f["path"]]) * math.log2(2 + lines) * _code_weight(f["path"])

    ranked = sorted(candidates, key=score, reverse=True)
    if category == "cicd":
        return ranked
    # Round-robin across top-level modules so one big package does not take
    # every slot: the grade is for the whole project.
    by_module: dict[str, list[dict]] = defaultdict(list)
    for f in ranked:
        by_module["/".join(f["path"].split("/")[:2])].append(f)
    queues = sorted(by_module.values(), key=lambda q: -score(q[0]))
    ordered: list[dict] = []
    while any(queues):
        for queue in queues:
            if queue:
                ordered.append(queue.pop(0))
    return ordered


def _render_head_file(f: dict, category: str, max_tokens: int) -> tuple[str, Range] | None:
    lines = f["content"].splitlines()
    total = len(lines)
    if total == 0:
        return None
    take = min(total, _FILE_LINE_CAPS.get(category, 150))
    while take >= min(total, _MIN_FILE_SLICE_LINES):
        body = "\n".join(f"{n:>4}| {_clip(line)}" for n, line in enumerate(lines[:take], start=1))
        header = (
            f"=== FILE {f['path']} (lines 1-{take} of {total}) | "
            f"cite as {_anchor(f['path'], 1, take)} or a narrower range ==="
        )
        text = header + "\n" + body
        if estimate_tokens(text) <= max_tokens:
            return text, (1, take)
        take = int(take * 0.7)
    return None


# Definition lines across the languages student projects use: Python/JS/TS
# functions and classes, Java/C#/Kotlin members, Go/Rust items, React
# components declared as consts, and test cases (it/test/describe).
_DEFINITION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:def|class|function|interface|enum|record|struct|trait|impl|func|fn|type)\s+\w"
    r"|^\s*(?:public|private|protected|internal)\s+[\w<>\[\],.?\s]*?\w+\s*\("
    r"|^\s*(?:public|private|protected|internal)?\s*(?:abstract\s+|static\s+|final\s+)*"
    r"(?:class|interface|enum|record)\s+\w"
    r"|^\s*(?:export\s+)?const\s+[A-Z]\w*\s*=\s*(?:async\s*)?\("
    r"|^\s*(?:it|test|describe)\(\s*['\"`]"
    r"|^\s*@(?:Test|ParameterizedTest|GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\b"
)
_MAX_OUTLINE_DEFS_PER_FILE = 10


def _outline_file(f: dict) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(f["content"].splitlines(), start=1):
        if _DEFINITION_RE.match(line):
            found.append((number, _first_line(line.strip().rstrip("{:").strip(), 70)))
            if len(found) >= _MAX_OUTLINE_DEFS_PER_FILE:
                break
    return found


def _render_outline(files: list[dict], budget: int, index: EvidenceIndex, stats: PackStats) -> str:
    """Signatures (with line numbers) of files whose contents are not shown,
    so the model can see the shape of the whole codebase cheaply."""
    header = (
        "CODE OUTLINE of files whose full contents are not shown: definition lines with their "
        "line numbers at HEAD. Cite one as path:L<n>."
    )
    lines = [header]
    used = estimate_tokens(header)
    for f in files:
        definitions = _outline_file(f)
        if not definitions:
            continue
        entry = f"{f['path']} ({f.get('line_count')} lines): " + "; ".join(
            f"L{n} {text}" for n, text in definitions
        )
        cost = estimate_tokens(entry) + 1
        if used + cost > budget:
            continue
        lines.append(entry)
        used += cost
        index.head_lines.setdefault(f["path"], []).extend((n, n) for n, _ in definitions)
        stats.outline_files += 1
    return "\n".join(lines) if len(lines) > 1 else ""


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _render_diff(diff: str, max_lines: int) -> tuple[list[str], list[int]]:
    """Unified diff -> lines prefixed with NEW-file line numbers (removed
    lines have none), plus the new-file line numbers shown."""
    out: list[str] = []
    shown: list[int] = []
    new_line: int | None = None
    for raw in diff.splitlines():
        if len(out) >= max_lines:
            break
        match = _HUNK_RE.match(raw)
        if match:
            new_line = int(match.group(1))
            out.append(f"@@ new L{new_line} @@")
            continue
        if new_line is None or raw.startswith("\\"):
            continue
        if raw.startswith("-"):
            out.append(f"     - {_clip(raw[1:])}")
            continue
        marker = "+" if raw.startswith("+") else " "
        out.append(f"{new_line:>4}{marker} {_clip(raw[1:])}")
        shown.append(new_line)
        new_line += 1
    return out, shown


def _diff_candidates(commits: list[dict], category: str, skip_added_paths: set[str]) -> list[tuple[dict, dict, float]]:
    candidates = []
    for commit in commits:
        for f in _relevant_files(commit, category):
            if not f.get("diff"):
                continue
            if f.get("change_type") == "added" and f["filename"] in skip_added_paths:
                continue  # whole file already shown at HEAD
            added = f.get("lines_added", 0)
            # Prefer substantive but reviewable changes; huge additions are
            # usually scaffolding or generated code.
            size = 0.1 if added < 3 else min(added, 300) / 300
            if added > 1500:
                size = 0.3
            candidates.append((commit, f, size * _code_weight(f["filename"])))
    return candidates


def _round_robin_by_author(candidates: list[tuple[dict, dict, float]]) -> list[tuple[dict, dict]]:
    by_author: dict[str, list[tuple[dict, dict, float]]] = defaultdict(list)
    for item in candidates:
        by_author[str(item[0].get("author"))].append(item)
    queues = [sorted(q, key=lambda item: -item[2]) for _, q in sorted(by_author.items())]
    ordered: list[tuple[dict, dict]] = []
    seen_paths: set[str] = set()
    deferred: list[tuple[dict, dict]] = []
    while any(queues):
        for queue in queues:
            if not queue:
                continue
            commit, f, _ = queue.pop(0)
            # Distinct files first; repeats of a file only after every file
            # has had a turn.
            if f["filename"] in seen_paths:
                deferred.append((commit, f))
            else:
                seen_paths.add(f["filename"])
                ordered.append((commit, f))
    return ordered + deferred


def _render_diff_excerpt(commit: dict, f: dict, max_tokens: int) -> tuple[str, list[int]] | None:
    limit = MAX_DIFF_LINES
    while limit >= _MIN_DIFF_SLICE_LINES:
        body, shown = _render_diff(f["diff"], limit)
        if not shown:
            return None  # pure deletion: nothing citable by line
        span = _anchor(f["filename"], min(shown), max(shown), commit["sha"])
        header = (
            f"=== DIFF {commit['sha'][:7]} | {str(commit.get('timestamp') or '')[:10]} | "
            f"{commit.get('author')} | \"{_first_line(commit.get('message', ''), 80)}\" | "
            f"{f['filename']} ({f.get('change_type', 'modified')}, +{f.get('lines_added', 0)}"
            f"/-{f.get('lines_deleted', 0)}) | cite as {span} or a narrower range ==="
        )
        cut = len(body) >= limit or f.get("diff_truncated")
        text = header + "\n" + "\n".join(body) + ("\n     … (diff continues)" if cut else "")
        if estimate_tokens(text) <= max_tokens:
            return text, shown
        limit = int(limit * 0.6)
    return None


# ── Entry point ────────────────────────────────────────────────────────────

def pack_dimension_evidence(
    bundle: dict,
    dimension: str,
    fields: tuple[str, ...],
    token_budget: int,
) -> PackedEvidence:
    """Render one dimension's evidence within `token_budget` estimated tokens.

    `bundle` is `ArtifactBundle.model_dump(mode="json")`; `fields` is the
    dimension's entry in llm_client._DIMENSION_ARTIFACT_FIELDS.
    """
    plan = _PLANS.get(dimension, _DimensionPlan(None, 0.4, 0.0))
    snapshot = bundle.get("repo_snapshot") or None
    index = EvidenceIndex(head_sha=(snapshot or {}).get("head_sha"))
    stats = PackStats(budget_tokens=token_budget)
    sections: list[str] = []
    remaining = token_budget - _COVERAGE_NOTE_TOKENS

    def add(section: str) -> None:
        nonlocal remaining
        if section:
            sections.append(section)
            remaining -= estimate_tokens(section) + 1

    add(_render_fixed_inputs(bundle, fields, index))

    commits = sorted(
        (_normalise_paths(c) for c in bundle.get("commits") or []),
        key=lambda c: str(c.get("timestamp") or ""),
    )
    for commit in commits:
        index.known_paths.update(f["filename"] for f in commit.get("files_changed") or [])
    if "commits" in fields:
        # Bundles ingested before diffs/snapshots existed have no file
        # content to save room for, so the ledger may use the whole budget.
        has_file_evidence = snapshot is not None or any(
            f.get("diff") for c in commits for f in c.get("files_changed") or []
        )
        share = plan.ledger_share if has_file_evidence and plan.category else max(plan.ledger_share, 0.9)
        add(_render_ledger(commits, plan.category, int(remaining * share), index, stats))

    category = plan.category
    if "commits" in fields and category:
        if snapshot:
            add(_render_tree(snapshot, int(remaining * 0.20), index, stats))
        churn: Counter[str] = Counter(
            f["filename"] for c in commits for f in c.get("files_changed") or []
        )
        head_queue = _rank_head_files(snapshot, category, churn) if snapshot else []
        stats.head_candidates = len(head_queue)
        shown_in_full: set[str] = set()

        def fill_head(budget: int) -> None:
            spent = 0
            too_big: list[dict] = []
            while head_queue and budget - spent > 200:
                f = head_queue.pop(0)
                rendered = _render_head_file(f, category, budget - spent)
                if rendered is None:
                    too_big.append(f)  # keep it for the outline / later top-up
                    continue
                text, (start, end) = rendered
                add(text)
                spent += estimate_tokens(text) + 1
                index.head_lines.setdefault(f["path"], []).append((start, end))
                shown_in_full.add(f["path"])
                stats.head_files_shown += 1
                stats.head_lines_shown += end - start + 1
            head_queue[:0] = too_big

        fill_head(int(remaining * plan.head_share))
        if category in ("source", "test") and head_queue:
            add(_render_outline(list(head_queue), int(remaining * 0.35), index, stats))

        candidates = _diff_candidates(commits, category, shown_in_full)
        stats.diff_candidates = len(candidates)
        diff_commits: set[str] = set()
        diff_authors: set[str] = set()
        for commit, f in _round_robin_by_author(candidates):
            if remaining <= 150:
                break
            rendered = _render_diff_excerpt(commit, f, remaining - 50)
            if rendered is None:
                continue
            text, shown = rendered
            add(text)
            index.diff_lines.setdefault((f["filename"], commit["sha"]), []).extend(_merge_ranges(shown))
            if commit["sha"] not in index.commit_shas:
                index.commit_shas.append(commit["sha"])
            stats.diff_excerpts += 1
            diff_commits.add(commit["sha"])
            diff_authors.add(str(commit.get("author")))
        stats.diff_commits = len(diff_commits)
        stats.diff_authors = len(diff_authors)

        fill_head(remaining - 50)  # diffs ran out first: give HEAD the rest

    coverage = _coverage_note(plan, stats, snapshot is not None)
    text = coverage + "\n\n" + "\n\n".join(sections)
    stats.used_tokens = estimate_tokens(text)
    return PackedEvidence(text=text, index=index, stats=stats)


def _coverage_note(plan: _DimensionPlan, stats: PackStats, has_snapshot: bool) -> str:
    parts = ["EVIDENCE COVERAGE (what you can see below):"]
    if stats.commits_total:
        parts.append(f"- Commit ledger lists {stats.commits_listed} of {stats.commits_total} commits.")
    if plan.category:
        if has_snapshot:
            parts.append(
                f"- File tree lists all {stats.tree_files} files at HEAD; full contents are shown for "
                f"{stats.head_files_shown} of {stats.head_candidates} {plan.category} files "
                f"({stats.head_lines_shown} lines)"
                + (f", and a definition outline for {stats.outline_files} more." if stats.outline_files else ".")
            )
        else:
            parts.append("- No repository snapshot was supplied, so no file contents at HEAD are shown.")
        parts.append(
            f"- {stats.diff_excerpts} diff excerpt(s) from {stats.diff_commits} commit(s) by "
            f"{stats.diff_authors} author(s) are shown."
        )
        parts.append(
            "- Files listed in the tree but not shown still exist and count as part of the "
            "submission (e.g. a test file's presence is evidence of testing), but judge code "
            "quality only from content you can actually see."
        )
    return "\n".join(parts)
