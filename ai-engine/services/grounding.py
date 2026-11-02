"""
services/grounding.py

Shared logic for verifying that LLM-generated evidence citations actually
trace back to the real, ingested student artifact data — rather than to
example/fixture text, or to plausible-sounding but fabricated content.

Used by services/llm_client.py as a post-generation filter: rather than
failing an entire rubric dimension because one citation looks fabricated,
llm_client.py drops only the ungrounded citations and keeps the (already
valid) score/justification, so a single bad citation can no longer cause a
whole dimension to disappear from the assessment. The installed
Instructor/OpenAI integration forwards unknown keyword arguments to OpenAI,
so validation context cannot be passed through the completion call.

Kept in its own module (rather than inside llm_client.py or the schema file)
specifically to avoid a circular import: llm_client.py imports
RubricDimensionScore from the schema module, so the schema module can't also
import from llm_client.py.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Matches identifier-like substrings: commit SHAs, JIRA keys ("ENG-123"),
# filenames, metric names — the kind of hard anchor a real citation should
# contain, and a fabricated citation usually won't reproduce exactly.
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{3,}")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _collect_leaf_values(node: object, out: list[str]) -> None:
    # Walk only VALUES, never dict keys — schema field names like "commits"
    # or "jira_tickets" would otherwise contaminate the corpus and let a
    # citation containing the word "commit" match against the "commits" key.
    if isinstance(node, dict):
        for value in node.values():
            _collect_leaf_values(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_leaf_values(item, out)
    elif node is not None:
        out.append(str(node))


def _build_value_corpus(bundle_data: str) -> str:
    try:
        parsed = json.loads(bundle_data)
    except (json.JSONDecodeError, TypeError):
        # Not JSON for some reason — fall back to raw text rather than crash.
        return _normalize(bundle_data)
    values: list[str] = []
    _collect_leaf_values(parsed, values)
    return _normalize(" ".join(values))


def find_ungrounded_citations(bundle_data: str, citations: list) -> list:
    """
    Returns the subset of `citations` that cannot be traced back to
    `bundle_data` (the actual serialized ArtifactBundle sent to the model) —
    which is exactly the fingerprint of a hallucinated citation, regardless
    of whether it was copied from an example or fabricated outright.

    Each citation is an EvidenceCitation-like object/dict with an
    `identifier` field (duck-typed here, not imported, to avoid a circular
    import with the schema module). Only the identifier is checked against
    the bundle:
      (a) it appears near-verbatim in the bundle's data VALUES
          (whitespace/case-normalized), or
      (b) it contains at least one identifier-like token (a SHA, ticket key,
          filename, etc.) that appears verbatim among those values.
    (a) alone is too strict — the model may rephrase slightly around a real
    identifier. (b) alone is too loose — a common short word could
    coincidentally match. Requiring one or the other balances precision and
    recall. The free-text `reason` is intentionally NOT required to match
    bundle values verbatim — it's the model's own explanation, and real
    evaluative reasoning ("clear, professional commit message") will rarely
    quote the data back verbatim.

    The corpus is built from data VALUES only, not the raw JSON text — schema
    field names (e.g. "commits", "jira_tickets") must never count as evidence,
    or placeholder citations like "commit 1" would trivially match against the
    literal key name "commits" and pass.
    """
    corpus = _build_value_corpus(bundle_data)
    ungrounded = []
    for citation in citations:
        if isinstance(citation, dict):
            identifier = citation.get("identifier", "")
        else:
            identifier = getattr(citation, "identifier", None) or str(citation)

        norm_identifier = _normalize(identifier)
        if norm_identifier and norm_identifier in corpus:
            continue
        tokens = _TOKEN_PATTERN.findall(identifier)
        if any(_normalize(tok) in corpus for tok in tokens):
            continue
        ungrounded.append(citation)
    return ungrounded

# ── Resolving citations against the packed evidence ───────────────────────
#
# The evidence packer (services/evidence_packer.py) records every anchor it
# shows the model in an EvidenceIndex. resolve_citations matches each model
# citation against that index, rather than against free text, so a citation
# survives only if it points at something the model actually saw, and the
# result carries a structured location (file, lines, commit) for the UI.

_LINE_ANCHOR = re.compile(
    r"(?P<path>[\w.@+\-/]*[\w\-]\.?[\w\-]*)"           # path (must contain a dot or slash, checked below)
    r"(?::|#)L?(?P<start>\d+)(?:\s*[-–]\s*L?(?P<end>\d+))?"
    r"(?:\s*@\s*(?P<sha>[0-9a-fA-F]{7,40}))?"
)
# The same thing written as prose: "src/app.py lines 10-24", "app.py (line 7)".
_PROSE_LINES = re.compile(
    r"(?P<path>[\w.@+\-/]+\.\w+)[`'\"]?\s*[,(]?\s*lines?\s+L?(?P<start>\d+)"
    r"(?:\s*(?:-|–|to)\s*L?(?P<end>\d+))?",
    re.IGNORECASE,
)
_SHA =re.compile(r"\b[0-9a-fA-F]{7,40}\b")
_TICKET = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_PATH_TOKEN = re.compile(r"[\w.@+\-]+(?:/[\w.@+\-]+)*")


def _overlap(start: int, end: int, ranges: list[tuple[int, int]]) -> tuple[int, int] | None:
    """The largest piece of [start, end] that lies inside one shown range."""
    best: tuple[int, int] | None = None
    for low, high in ranges:
        lo, hi = max(start, low), min(end, high)
        if lo <= hi and (best is None or hi - lo > best[1] - best[0]):
            best = (lo, hi)
    return best


def _match_path(candidate: str, index: Any) -> str | None:
    candidate = candidate.strip().strip("`'\"").removeprefix("./").removeprefix("/")
    if candidate in index.known_paths:
        return candidate
    # Basename or path suffix only, when it is unambiguous.
    matches = [p for p in index.known_paths if p.endswith("/" + candidate)]
    return matches[0] if len(matches) == 1 else None


def _resolve_line_anchor(identifier: str, index: Any) -> dict | None:
    matches = [*_LINE_ANCHOR.finditer(identifier), *_PROSE_LINES.finditer(identifier)]
    for match in matches:
        raw_path = match.group("path")
        if "/" not in raw_path and "." not in raw_path:
            continue
        path = _match_path(raw_path, index)
        if path is None:
            continue
        start = int(match.group("start"))
        end = int(match.group("end") or start)
        start, end = min(start, end), max(start, end)
        sha_text = match.groupdict().get("sha")
        sha = index.find_commit(sha_text) if sha_text else None

        candidates: list[tuple[str | None, list[tuple[int, int]]]]
        if sha is not None:
            candidates = [(sha, index.diff_lines.get((path, sha), []))]
        elif sha_text:
            candidates = []  # names a commit the model was never shown
        else:
            # No commit given: HEAD contents first, then any diff that showed
            # these lines (most recent first).
            candidates = [(None, index.head_lines.get(path, []))]
            candidates += sorted(
                ((s, r) for (p, s), r in index.diff_lines.items() if p == path),
                key=lambda item: -index.commit_shas.index(item[0]) if item[0] in index.commit_shas else 0,
            )
        for commit_sha, ranges in candidates:
            clamped = _overlap(start, end, ranges)
            if clamped:
                lo, hi = clamped
                lines = f"L{lo}" if lo == hi else f"L{lo}-L{hi}"
                return {
                    "kind": "diff_lines" if commit_sha else "file_lines",
                    "identifier": f"{path}:{lines}" + (f"@{commit_sha[:7]}" if commit_sha else ""),
                    "file_path": path,
                    "line_start": lo,
                    "line_end": hi,
                    # HEAD lines carry the snapshot's SHA so a link pins the
                    # exact code that was graded, even after later pushes.
                    "commit_sha": commit_sha or index.head_sha,
                }
        # Real file, but those lines were never shown: keep it as a file
        # citation rather than trust model-invented line numbers.
        return {"kind": "file", "identifier": path, "file_path": path, "commit_sha": sha, "downgraded": True}
    return None


def resolve_citation(identifier: str, index: Any) -> dict | None:
    """Match one citation identifier to the EvidenceIndex. Returns the
    resolved location fields (including a canonical `identifier`), or None
    when it points at nothing the model was shown."""
    resolved = _resolve_line_anchor(identifier, index)
    if resolved:
        return resolved
    for token in _SHA.findall(identifier):
        sha = index.find_commit(token)
        if sha:
            return {"kind": "commit", "identifier": sha[:7], "commit_sha": sha}
    for ticket in _TICKET.findall(identifier):
        if ticket in index.tickets:
            return {"kind": "ticket", "identifier": ticket}
    for token in sorted(_PATH_TOKEN.findall(identifier), key=len, reverse=True):
        if ("/" in token or "." in token) and (path := _match_path(token, index)):
            return {"kind": "file", "identifier": path, "file_path": path}
    # A named metric that was shown, e.g. "completion_percent: 80". Matched by
    # name, since short values like 80 are too common to verify on their own.
    lowered = identifier.lower().replace(" ", "_")
    for name, value in index.metrics.items():
        if name.lower() in lowered:
            return {"kind": "other", "identifier": f"{name}={value}"}
    # Anything else: fall back to the value-corpus check over the non-commit
    # inputs the model was shown.
    if not find_ungrounded_citations(index.other_values_json, [{"identifier": identifier}]):
        return {"kind": "other", "identifier": identifier}
    return None


def resolve_citations(citations: list, index: Any) -> tuple[list[dict], list, int]:
    """Resolve every citation. Returns (resolved citation dicts, dropped
    citations, number downgraded from line- to file-level). Duplicates of an
    already-resolved location are dropped too."""
    resolved: list[dict] = []
    dropped: list = []
    downgraded = 0
    seen: set[str] = set()
    for citation in citations:
        data = citation.model_dump() if hasattr(citation, "model_dump") else dict(citation)
        location = resolve_citation(str(data.get("identifier", "")), index)
        if location is None:
            dropped.append(citation)
            continue
        if location.pop("downgraded", False):
            downgraded += 1
        if location["identifier"] in seen:
            continue
        seen.add(location["identifier"])
        resolved.append({"reason": data.get("reason", ""), **location})
    return resolved, dropped, downgraded
