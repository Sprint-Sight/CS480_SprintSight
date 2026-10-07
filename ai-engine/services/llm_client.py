import contextvars, hashlib, json, logging, os, time, httpx, instructor, mlflow
from collections import Counter
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from mlflow.entities import SpanType
from openai import AsyncOpenAI

from llmops.prompt_registry import (
    load_dimension_prompt,
    register_dimension_prompt,
)
from dotenv import load_dotenv
from mlflow.entities import SpanType
from openai import AsyncOpenAI

from prompts.templates import (
    render_dimension_prompt,
    render_sprint_feedback_prompt,
)
from schemas.artifact_bundle import ArtifactBundle
from schemas.modelname import MODEL_NUM_CTX
from schemas.rubrics_dimension_score import (
    DimensionName,
    ModelOutput,
    RubricDimensionScore,
)
from schemas.sprint_feedback import SprintFeedback
from services.audit_logger import write_audit_record
from services.grounding import find_ungrounded_citations

load_dotenv()  # Load environment variables from .env file

log = logging.getLogger(__name__)

"""
services/llm_client.py

One place in the entire codebase that knows how to talk to Ollama.
Every other file imports the client from here — never create the client
directly in other files.

How it works:
    Ollama runs inside Docker Compose at http://ollama:11434
    It exposes an OpenAI-compatible endpoint at /v1/chat/completions
    We use the OpenAI Python client pointing at that URL
    instructor wraps it to return Pydantic models instead of raw JSON
"""

# Read from .env file (set by Docker Compose environment block)
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")  # Ollama ignores this, but OpenAI client requires it
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434/v1")
OLLAMA_TIMEOUT  = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "1200"))

# json_schema constrains Ollama's decoding to the exact schema (no more
# invented field names, no need for _normalize_citation in the long run) but
# requires both `instructor` and the Ollama server to support OpenAI's
# `response_format: json_schema`. Neither version is pinned in
# requirements.txt/Ollama's image, so this is exposed as an env var rollback
# switch rather than hardcoded — verify with `ollama --version` / `pip show
# instructor` before trusting it in prod, and flip back to "json" if the
# server rejects it.
_INSTRUCTOR_MODES = {"json": instructor.Mode.JSON, "json_schema": instructor.Mode.JSON_SCHEMA}
_STRUCTURED_OUTPUT_MODE = os.getenv("LLM_STRUCTURED_OUTPUT_MODE", "json_schema").strip().lower()

CODE_DIMENSIONS = {"code_quality", "testing"}
DOCUMENTATION_DIMENSIONS = {"documentation"}

def _with_line_numbers(content: str) -> str:
    return "\n".join(f"{i+1}: {line}" for i, line in enumerate(content.splitlines()))

def _bundle_data_for_dimension(bundle: ArtifactBundle, dimension_name: str) -> str:
    """Dimension-scoped view of the bundle -- keeps prompts smaller for
    dimensions that don't need source content, and surfaces Java/README
    content (with line numbers, for citation grounding) for the ones that do."""
    payload: dict = {
        "team_id": bundle.team_id,
        "sprint_id": bundle.sprint_id,
        "commits": [c.model_dump(mode="json") for c in bundle.commits],
        "jira_tickets": [t.model_dump(mode="json") for t in bundle.jira_tickets],
        "peer_evaluations": [p.model_dump(mode="json") for p in bundle.peer_evaluations],
    }
    if dimension_name in CODE_DIMENSIONS:
        payload["code_files"] = [
            {"filename": f.filename, "content": _with_line_numbers(f.content)} for f in bundle.code_files
        ]
    if dimension_name in DOCUMENTATION_DIMENSIONS:
        payload["documents"] = [
            {"filename": f.filename, "content": _with_line_numbers(f.content)} for f in bundle.documents
        ]
    return json.dumps(payload, indent=2, default=str)

def _with_line_numbers(content: str) -> str:
    return "\n".join(f"{i+1}: {line}" for i, line in enumerate(content.splitlines()))

_audit_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "audit_context", default=None
)

# Extensions treated as data/generated output rather than authored logic when
# computing the "meaningful lines changed" fact below — e.g. exported test
# fixtures, logs, or generated JSON, which inflate line counts without
# reflecting engineering effort. Deliberately small/conservative: only
# extensions that are overwhelmingly non-code in this project's repos.
_LOW_SIGNAL_EXTENSIONS = {".txt", ".json"}

_NOISE_PATH_SEGMENTS = {
    "node_modules/", "vendor/", "venv/", ".venv/", "env/",
    "dist/", "build/", "out/", "__pycache__/", ".next/", ".nuxt/",
    "target/", "bower_components/", ".gradle/", ".m2/", "Pods/",
    "DerivedData/", ".terraform/", ".angular/", ".cache/",
}
_LOCKFILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "go.sum", "composer.lock",
    "Gemfile.lock", "shrinkwrap.yaml", "bun.lockb",
}
_GENERATED_EXTENSIONS = {".min.js", ".min.css", ".map", ".chunk.js", ".bundle.js"}
_MAX_FILES_PER_COMMIT = int(os.getenv("LLM_MAX_FILES_PER_COMMIT", "20"))

# Commit messages so generic they carry ~no information about what changed.
# Compared after stripping whitespace and lowercasing.
_GENERIC_COMMIT_MESSAGES = {
    "update", "updates", "updated", "fix", "fixes", "wip", "misc",
    "changes", "minor changes", "init", "initial commit", "init commit",
    "commit", "stuff", "asdf", "test",
}

_COMMIT_BUDGET = int(os.getenv("LLM_COMMIT_BUDGET", "30"))

_DIMENSION_FILE_PATTERNS: dict[str, list[str] | None] = {
    "code_quality": None,
    "testing": [
        "test", "spec", "__test__", "_test.", ".test.", "coverage",
    ],
    "documentation": [
        "readme", ".md", "docs/", "doc/", "changelog", "license",
        "contributing",
    ],
    "cicd": [
        ".github/", ".gitlab-ci", "dockerfile", "docker-compose",
        "makefile", "deploy", "workflow",
        "pipeline", "ci/", "terraform",
    ],
}

_DIMENSION_ARTIFACT_FIELDS = {
    "code_quality": ("commits",),
    "testing": ("commits", "jira_tickets", "artifact_metrics"),
    "documentation": ("commits", "jira_tickets"),
    "requirements": ("jira_tickets", "artifact_metrics"),
    "collaboration": (
        "jira_tickets",
        "peer_evaluations",
        "collaboration_metrics",
    ),
    "cicd": ("commits", "artifact_metrics"),
}


def _is_noise_file(path: str) -> bool:
    lower = path.lower().replace("\\", "/")
    if any(seg in lower for seg in _NOISE_PATH_SEGMENTS):
        return True
    basename = lower.rsplit("/", 1)[-1]
    if basename in _LOCKFILE_NAMES:
        return True
    return any(basename.endswith(ext) for ext in _GENERATED_EXTENSIONS)


def _trim_commits(raw_commits: list[dict]) -> list[dict]:
    result = []
    for c in raw_commits:
        files = [fc["filename"] for fc in c["files_changed"]]
        files = [f for f in files if not _is_noise_file(f)]
        if len(files) > _MAX_FILES_PER_COMMIT:
            files = files[:_MAX_FILES_PER_COMMIT]
        result.append({
            "sha": c["sha"],
            "author": c["author"],
            "message": c["message"],
            "timestamp": c["timestamp"],
            "lines_added": c["lines_added"],
            "lines_deleted": c["lines_deleted"],
            "files_changed": files,
        })
    return result


def _commit_matches_patterns(commit: dict, patterns: list[str]) -> bool:
    files = commit.get("files_changed", [])
    return any(
        any(p in fname.lower() for p in patterns) for fname in files
    )


def _select_representative_commits(
    commits: list[dict],
    dimension: str,
    budget: int = _COMMIT_BUDGET,
) -> list[dict]:
    if len(commits) <= budget:
        return commits

    patterns = _DIMENSION_FILE_PATTERNS.get(dimension)
    selected_shas: set[str] = set()
    result: list[dict] = []

    def _add(c: dict) -> bool:
        if c["sha"] in selected_shas:
            return False
        selected_shas.add(c["sha"])
        result.append(c)
        return True

    if patterns is not None:
        matched = [c for c in commits if _commit_matches_patterns(c, patterns)]
        unmatched = [c for c in commits if not _commit_matches_patterns(c, patterns)]
        for c in matched[:budget]:
            _add(c)
        by_date = sorted(unmatched, key=lambda c: c.get("timestamp", ""), reverse=True)
        for c in by_date:
            if len(result) >= budget:
                break
            _add(c)
    else:
        by_churn = sorted(
            commits,
            key=lambda c: c.get("lines_added", 0) + c.get("lines_deleted", 0),
            reverse=True,
        )
        by_date = sorted(commits, key=lambda c: c.get("timestamp", ""), reverse=True)
        for c in by_date[: budget // 2]:
            _add(c)
        for c in by_churn:
            if len(result) >= budget:
                break
            _add(c)

    return sorted(result, key=lambda c: c.get("timestamp", ""))


def _compute_jira_facts(tickets: list[dict]) -> str:
    if not tickets:
        return ""

    by_status: dict[str, int] = Counter(t.get("status") or "Unknown" for t in tickets)
    by_type: dict[str, int] = Counter(t.get("issue_type") or "Unknown" for t in tickets)

    estimated = [t for t in tickets if t.get("story_points") is not None]
    total_sp = sum(t["story_points"] for t in estimated)
    done_sp = sum(
        t["story_points"] for t in estimated if t.get("status") == "Done"
    )
    unestimated_count = len(tickets) - len(estimated)
    sp_pct = (done_sp / total_sp * 100) if total_sp > 0 else 0

    assignees: dict[str, dict] = {}
    for t in tickets:
        a = t.get("assignee") or "Unassigned"
        if a not in assignees:
            assignees[a] = {"done": 0, "total": 0, "sp_done": 0.0, "sp_total": 0.0}
        assignees[a]["total"] += 1
        sp = t.get("story_points") or 0
        assignees[a]["sp_total"] += sp
        if t.get("status") == "Done":
            assignees[a]["done"] += 1
            assignees[a]["sp_done"] += sp

    status_str = ", ".join(f"{cnt} {st}" for st, cnt in sorted(by_status.items(), key=lambda x: -x[1]))
    type_str = ", ".join(f"{cnt} {tp}" for tp, cnt in sorted(by_type.items(), key=lambda x: -x[1]))
    assignee_parts = []
    for name, d in sorted(assignees.items()):
        assignee_parts.append(
            f"{name} ({d['done']}/{d['total']} Done, {d['sp_done']:.0f}/{d['sp_total']:.0f} SP)"
        )

    lines = [
        "Jira ticket facts (trust these over your own counting):",
        f"- {len(tickets)} ticket(s) total: {status_str}.",
        f"- Story points: {done_sp:.0f} of {total_sp:.0f} completed ({sp_pct:.1f}%).",
        f"- By type: {type_str}.",
        f"- Per-assignee: {'; '.join(assignee_parts)}.",
    ]
    if unestimated_count:
        lines.append(
            f"- {unestimated_count} ticket(s) have no story point estimate."
        )
    return "\n    ".join(lines)


def _dimension_bundle_data(
    bundle: ArtifactBundle,
    dimension_name: str,
    sampled_commits: list[dict] | None = None,
) -> str:
    fields = _DIMENSION_ARTIFACT_FIELDS.get(dimension_name)
    if fields is None:
        raise ValueError(f"Unknown rubric dimension: {dimension_name}")

    full_bundle = bundle.model_dump(mode="json")
    bundle_data: dict[str, Any] = {
        "team_id": bundle.team_id,
        "sprint_id": bundle.sprint_id,
        "instructor_expectations": bundle.instructor_expectations,
    }

    if "commits" in fields:
        if sampled_commits is not None:
            bundle_data["commits"] = sampled_commits
        else:
            bundle_data["commits"] = _trim_commits(full_bundle["commits"])

    for field in fields:
        if field != "commits":
            bundle_data[field] = full_bundle[field]

    return json.dumps(bundle_data, indent=2, ensure_ascii=True)


def _compute_commit_facts(commits: list[dict], budget: int = _COMMIT_BUDGET) -> str:
    """
    Precomputes objective facts about a dimension's commit list so the model
    has the full statistical picture even when only a sample of commits is
    included in the bundle.  Returns "" when there are no commits.
    """
    if not commits:
        return ""

    authors = sorted({commit["author"] for commit in commits if commit.get("author")})
    active_days = sorted({commit["timestamp"][:10] for commit in commits if commit.get("timestamp")})

    lines_added_total = sum(commit.get("lines_added", 0) for commit in commits)
    lines_deleted_total = sum(commit.get("lines_deleted", 0) for commit in commits)

    meaningful_lines_added = 0
    for commit in commits:
        files_changed = commit.get("files_changed") or []
        if not files_changed:
            meaningful_lines_added += commit.get("lines_added", 0)
            continue
        for filename in files_changed:
            if PurePosixPath(filename).suffix.lower() not in _LOW_SIGNAL_EXTENSIONS:
                meaningful_lines_added += commit.get("lines_added", 0)
                break

    message_counts = Counter(
        (commit.get("message") or "").strip().lower() for commit in commits
    )
    generic_count = sum(
        count for message, count in message_counts.items() if message in _GENERIC_COMMIT_MESSAGES
    )
    generic_examples = sorted(
        {message for message in message_counts if message in _GENERIC_COMMIT_MESSAGES}
    )[:3]

    # ── Per-author breakdown ──
    author_stats: dict[str, dict] = {}
    for commit in commits:
        a = commit.get("author") or "unknown"
        if a not in author_stats:
            author_stats[a] = {"commits": 0, "added": 0, "deleted": 0, "days": set()}
        author_stats[a]["commits"] += 1
        author_stats[a]["added"] += commit.get("lines_added", 0)
        author_stats[a]["deleted"] += commit.get("lines_deleted", 0)
        ts = commit.get("timestamp", "")
        if ts:
            author_stats[a]["days"].add(ts[:10])

    author_lines = []
    for name in sorted(author_stats, key=lambda n: -author_stats[n]["commits"]):
        s = author_stats[name]
        author_lines.append(
            f"  {name}: {s['commits']} commits, "
            f"+{s['added']}/-{s['deleted']} lines, "
            f"{len(s['days'])} active day(s)"
        )

    # ── File change heatmap (top 10) ──
    file_freq: Counter[str] = Counter()
    for commit in commits:
        for fname in commit.get("files_changed") or []:
            file_freq[fname] += 1
    heatmap_lines = [
        f"  {fname}: {cnt} commit(s)" for fname, cnt in file_freq.most_common(10)
    ]

    lines = [
        "Computed facts (trust these over your own counting):",
        (
            f"- {len(commits)} commit(s) by {', '.join(authors) or 'unknown author(s)'} "
            f"across {len(active_days)} active day(s): {', '.join(active_days) or 'unknown dates'}."
        ),
        (
            f"- {lines_added_total} lines added, {lines_deleted_total} lines deleted in total "
            f"({meaningful_lines_added} added lines are in non-{'/'.join(sorted(_LOW_SIGNAL_EXTENSIONS))} files)."
        ),
        f"- {generic_count} of {len(commits)} commit message(s) are generic/low-detail "
        f"(e.g. {', '.join(repr(m) for m in generic_examples) or 'none'})." if generic_count
        else f"- 0 of {len(commits)} commit message(s) are generic/low-detail.",
        "",
        "Per-author breakdown:",
        *author_lines,
        "",
        "Most-changed files (top 10):",
        *(heatmap_lines or ["  (no file data)"]),
    ]

    if len(commits) > budget:
        lines.append(
            f"\nNOTE: {len(commits)} total commits; the {budget} most representative "
            f"are included below as citable evidence."
        )

    return "\n    ".join(lines)


def _request_extra_body(num_ctx: int | None) -> dict:
    if num_ctx is None:
        return {}
    return {"options": {"num_ctx": num_ctx}}


def estimate_dimension_tokens(bundle: ArtifactBundle, dimension_name: str) -> int:
    """Rough token estimate (chars // 4) for one dimension's trimmed bundle."""
    return len(_dimension_bundle_data(bundle, dimension_name)) // 4


# Minimum num_ctx to fall back to when a sprint's bundle is small. Defaults to
# None (disabled): by default this NEVER reduces num_ctx below the model's
# full configured ceiling (e.g. the 49152 set in models/Modelfile.llama and
# mirrored in MODEL_NUM_CTX) — chars//4 is only an estimate, and silently
# undershooting num_ctx means Ollama truncates context with no error, which is
# unacceptable for a grading tool. Only opt into a smaller floor (e.g. 8192)
# via LLM_NUM_CTX_FLOOR once you've verified with `ollama ps` that your actual
# bundles are consistently far below the ceiling.
_NUM_CTX_FLOOR = int(os.getenv("LLM_NUM_CTX_FLOOR", "0")) or None


def select_run_num_ctx(bundle: ArtifactBundle, model_name: str, dimension_names: Sequence[str]) -> int | None:
    """
    Picks ONE num_ctx value to reuse across every `evaluate_dimension` call
    for this sprint's evaluation run. This must be computed ONCE per sprint
    (not per-dimension): Ollama reloads the model whenever num_ctx changes
    between requests, and per-dimension bundles vary in size (code_quality
    only gets commits; testing/cicd get more), so sizing per-call would force
    a reload before nearly every one of the ~6-7 calls in a single run.
    Never exceeds the model's configured ceiling in schemas/modelname.py, and
    by default (LLM_NUM_CTX_FLOOR unset) never goes below it either — see
    _NUM_CTX_FLOOR above.
    """
    ceiling = MODEL_NUM_CTX.get(model_name)
    if ceiling is None:
        log.warning(
            "No known num_ctx ceiling for model '%s' — omitting num_ctx override "
            "so Ollama uses the model's own manifest value.",
            model_name,
        )
        return None
    if _NUM_CTX_FLOOR is None:
        return ceiling
    largest_prompt_tokens = max(
        (estimate_dimension_tokens(bundle, dim) for dim in dimension_names),
        default=0,
    )
    needed = largest_prompt_tokens + 1024  # headroom for prompt scaffolding + generated output
    return min(max(needed, _NUM_CTX_FLOOR), ceiling)


async def _capture_request(request: httpx.Request) -> None:
    if request.url.path.endswith("/chat/completions"):
        context = _audit_context.get()
        if context is not None:
            context["request_started_at"] = time.perf_counter()
            context["request"] = request.content.decode("utf-8", errors="replace")

async def _capture_response(response: httpx.Response) -> None:
    if response.request.url.path.endswith("/chat/completions"):
        context = _audit_context.get()
        if context is not None:
            body = await response.aread()
            started_at = context.get("request_started_at", time.perf_counter())
            write_audit_record(
                {
                    **context,
                    "request": json.loads(context.get("request", "{}")),
                    "raw_response": body.decode("utf-8", errors="replace"),
                    "http_status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                }
            )


def create_llm_client(provider="ollama"):
    """
    Creates the instructor-wrapped Ollama client.

    Call this ONCE in your FastAPI lifespan and store it as a module-level
    variable. Do NOT call this per-request.

    Structured-output mode is controlled by LLM_STRUCTURED_OUTPUT_MODE (see
    top of file): "json_schema" constrains Ollama's decoding to the exact
    schema; "json" (the old default) only guarantees valid JSON, not the
    right keys. Falls back to JSON mode for any unrecognized value.
    """
    transport = httpx.AsyncClient( # Create a custom HTTP transport to capture requests and responses for auditing
        event_hooks={
            "request": [_capture_request],   # Capture the request before sending it to Ollama
            "response": [_capture_response], # Capture the response after receiving it from Ollama
        }
    )

    if provider == "ollama":
        raw_client = AsyncOpenAI( # Create an OpenAI-compatible client pointing at Ollama
            base_url=OLLAMA_BASE_URL,
            api_key=OLLAMA_API_KEY,
            timeout=OLLAMA_TIMEOUT,
            http_client=transport, # Use the custom transport to capture requests and responses
        )
    if provider == "openai":
        raw_client = AsyncOpenAI( # Create an OpenAI-compatible client pointing at Ollama
            base_url=OLLAMA_BASE_URL,
            api_key=OLLAMA_API_KEY,
            timeout=OLLAMA_TIMEOUT,
            http_client=transport, # Use the custom transport to capture requests and responses
        )

    client = instructor.from_openai( # Wrap OpenAI client with instructor to return Pydantic models instead of raw JSON
        raw_client, # The raw OpenAI-compatible client pointing at Ollama
        mode=instructor.Mode.JSON, # ensures that the response is parsed as JSON, returned as a Pydantic model
    )
    return client

# # Each child span of the parent span (Evaluate_Complete_Sprint)
# @mlflow.trace(name="Evaluate_Dimension", span_type=SpanType.LLM)
# async def evaluate_dimension(bundle: ArtifactBundle, dimension_name: str, model_name: str) -> RubricDimensionScore:
#     # Asynchronously evaluates a single rubric dimension to ensure fast concurrent processing.
#     # bundle_data = bundle.model_dump_json(indent=2) # json representation of the bundle for logging and debugging
#         raw_client,
#         # Actually honor LLM_STRUCTURED_OUTPUT_MODE instead of always using
#         # JSON mode -- JSON mode only describes the schema in the prompt, so
#         # weak models can literally echo the schema back as their "answer"
#         # instead of an instance of it. JSON_SCHEMA mode constrains Ollama's
#         # decoding to the real schema and avoids that failure mode.
#         mode=_INSTRUCTOR_MODES.get(_STRUCTURED_OUTPUT_MODE, instructor.Mode.JSON),
#     )
#     return client

# Each child span of the parent span (Evaluate_Complete_Sprint)
@mlflow.trace(name="Evaluate_Dimension", span_type=SpanType.LLM)
async def evaluate_dimension(
    bundle: ArtifactBundle,
    dimension_name: DimensionName,
    model_name: str,
    dimention_prompt,
    num_ctx: int | None = None,
) -> RubricDimensionScore:
    # Evaluate a single rubric dimension.
    fields = _DIMENSION_ARTIFACT_FIELDS.get(dimension_name, ())
    full_bundle = bundle.model_dump(mode="json")

    # ── Stats from ALL commits, then sample for the bundle ──
    sampled_commits: list[dict] | None = None
    if "commits" in fields:
        all_trimmed = _trim_commits(full_bundle["commits"])
        commit_facts = _compute_commit_facts(all_trimmed, _COMMIT_BUDGET)
        sampled_commits = _select_representative_commits(
            all_trimmed, dimension_name, _COMMIT_BUDGET,
        )
        log.info(
            ">>> Dimension '%s': %d total commits -> %d sampled (budget=%d)",
            dimension_name, len(all_trimmed), len(sampled_commits), _COMMIT_BUDGET,
        )
    else:
        commit_facts = ""

    jira_facts = (
        _compute_jira_facts(full_bundle["jira_tickets"])
        if "jira_tickets" in fields else ""
    )

    computed_facts = "\n\n    ".join(filter(None, [commit_facts, jira_facts]))

    bundle_data = _dimension_bundle_data(bundle, dimension_name, sampled_commits)
    bundle_hash = hashlib.sha256(
        bundle_data.encode("utf-8")
    ).hexdigest()

    approx_tokens = len(bundle_data) // 4
    log.info(
        ">>> Dimension '%s': bundle_data is %d chars (~%d tokens estimated)",
        dimension_name,
        len(bundle_data),
        approx_tokens,
    )

    effective_ctx = num_ctx or MODEL_NUM_CTX.get(model_name, 49152)
    if approx_tokens > effective_ctx * 0.85:
        log.warning(
            ">>> Dimension '%s': prompt (~%d tokens) approaches num_ctx (%d). "
            "Output quality may degrade from silent truncation.",
            dimension_name, approx_tokens, effective_ctx,
        )

    prompt = render_dimension_prompt(dimension_name, dimention_prompt, bundle_data, computed_facts)

    client = create_llm_client()  # Create a new client for this model

    audit_token = _audit_context.set(
        {
            "request_id": str(uuid4()),
            "team_id": bundle.team_id,
            "sprint_id": bundle.sprint_id,
            "dimension": dimension_name,
            "model": model_name,
            "bundle_hash": bundle_hash,
            "bundle_bytes": len(bundle_data.encode("utf-8")),
            "commit_count": len(bundle.commits),
            "jira_ticket_count": len(bundle.jira_tickets),
            "peer_evaluation_count": len(bundle.peer_evaluations),
            "artifact_metric_keys": sorted(bundle.artifact_metrics),
        }
    )
    try:
        # The transport hooks capture the exact request and raw Ollama response.
        model_output = await client.chat.completions.create(
            model=model_name,
            response_model=ModelOutput,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_retries=3,
            extra_body=_request_extra_body(num_ctx),
        )

        # dimension/evaluation_failed are assigned here, in code, rather than
        # asked of the model — it can't get the dimension wrong if it's never
        # given the chance to answer it.
        result = RubricDimensionScore(
            dimension=dimension_name,
            **model_output.model_dump(),
        )

        # Drop only fabricated/ungrounded citations rather than discarding
        # the whole dimension over a single bad citation.
        ungrounded = find_ungrounded_citations(
            bundle_data,
            result.evidence_citations or [],
        )

        if ungrounded:
            log.warning(
                "Dimension '%s': dropping %d ungrounded citation(s) "
                "rather than failing the whole dimension: %r",
                dimension_name,
                len(ungrounded),
                ungrounded,
            )

            write_audit_record(
                {
                    **(_audit_context.get() or {}),
                    "ungrounded_citations_dropped": [
                        (
                            citation.model_dump()
                            if hasattr(citation, "model_dump")
                            else citation
                        )
                        for citation in ungrounded
                    ],
                }
            )

            result.evidence_citations = [
                citation
                for citation in (result.evidence_citations or [])
                if citation not in ungrounded
            ]

        return result

    except Exception as error:
        context = _audit_context.get()

        write_audit_record(
            {
                **(context or {}),
                "error": str(error),
            }
        )
        raise

    finally:
        _audit_context.reset(audit_token)


async def generate_sprint_feedback(
    bundle: ArtifactBundle,
    rubric_scores: dict[str, dict],
    model_name: str,
    num_ctx: int | None = None,
) -> SprintFeedback:
    """Generate strengths, weaknesses, and recommendations for the whole sprint."""
    scores_data = json.dumps(rubric_scores, indent=2, ensure_ascii=True, default=str)
    prompt = render_sprint_feedback_prompt(
        bundle.team_id, bundle.sprint_id, scores_data, bundle.instructor_expectations
    )
    audit_token = _audit_context.set(
        {
            "request_id": str(uuid4()),
            "team_id": bundle.team_id,
            "sprint_id": bundle.sprint_id,
            "dimension": "sprint_feedback",
            "model": model_name,
        }
    )
    try:
        client = create_llm_client()
        full_prompt_chars = len(prompt)
        log.info(
            ">>> Dimension '%s': full user-message prompt is %d chars (~%d tokens estimated)",
            "sprint_feedback", full_prompt_chars, full_prompt_chars // 4,
        )
        return await client.chat.completions.create(
            model=model_name,
            response_model=SprintFeedback,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_retries=3,
            extra_body=_request_extra_body(num_ctx),
        )
    finally:
        _audit_context.reset(audit_token)


async def check_ollama_health(model_name: str) -> dict:
    """
    Verifies that Ollama is running and the target model is available.
    Called from the FastAPI startup health check.

    Returns a dict:
        {"status": "ok",    "model": "llama3.1:8b", "available": True}
        {"status": "error", "model": "llama3.1:8b", "error": "..."}
    """
    # Ollama's /api/tags lists downloaded models
    tags_url = OLLAMA_BASE_URL.replace("/v1", "") + "/api/tags"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(tags_url)
            response.raise_for_status()
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            available = any(model_name in name for name in model_names)

            if not available:
                log.warning(
                    "Ollama is running but model '%s' is not downloaded. "
                    "Run: docker exec <ollama_container> ollama pull %s",
                    model_name, model_name,
                )

            return {
                "status":    "ok",
                "model":     model_name,
                "available": available,
                "all_models": model_names,
            }

    except httpx.ConnectError:
        return {
            "status": "error",
            "model":  model_name,
            "error":  f"Cannot connect to Ollama at {tags_url}. Is it running?",
        }
    except Exception as e:  # noqa: BLE001 - health check must report status, not raise
        return {
            "status": "error",
            "model":  model_name,
            "error":  str(e),
        }


async def pull_model_if_missing(model_name: str) -> None:
    """
    Triggers an Ollama model pull if the model is not already downloaded.
    Called once at service startup. This can take several minutes for large
    models — that is expected and normal.
    """
    health = await check_ollama_health(model_name)
    if health.get("available"):
        log.info("Model '%s' already available in Ollama.", model_name)
        return

    pull_url = OLLAMA_BASE_URL.replace("/v1", "") + "/api/pull"
    log.info("Pulling model '%s' — this may take several minutes...", model_name)

    try:
        async with httpx.AsyncClient(timeout=1800.0) as client, client.stream("POST", pull_url, json={"name": model_name}) as resp:   # 30 min timeout
            async for line in resp.aiter_lines():
                if line:
                    log.debug("Pull progress: %s", line)
        log.info("Model '%s' downloaded successfully.", model_name)
    except Exception as e:
        log.error("Failed to pull model '%s': %s", model_name, e)
        raise