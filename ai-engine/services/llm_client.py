import contextvars
import hashlib
import json
import logging
import os
import time
from collections import Counter
from pathlib import PurePosixPath
from typing import Any, Sequence
from uuid import uuid4

import httpx
import instructor
import mlflow
from dotenv import load_dotenv
from mlflow.entities import SpanType
from openai import AsyncOpenAI

from prompts.templates import (
    render_dimension_prompt,
    render_sprint_feedback_prompt,
)
from schemas.artifact_bundle import ArtifactBundle
from schemas.modelname import MODEL_NUM_CTX
from schemas.rubrics_dimension_score import DimensionName, ModelOutput, RubricDimensionScore
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

# Commit messages so generic they carry ~no information about what changed.
# Compared after stripping whitespace and lowercasing.
_GENERIC_COMMIT_MESSAGES = {
    "update", "updates", "updated", "fix", "fixes", "wip", "misc",
    "changes", "minor changes", "init", "initial commit", "init commit",
    "commit", "stuff", "asdf", "test",
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


def _dimension_bundle_data(bundle: ArtifactBundle, dimension_name: str) -> str:
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
        bundle_data["commits"] = [
            {
                "sha": commit["sha"],
                "author": commit["author"],
                "message": commit["message"],
                "timestamp": commit["timestamp"],
                "lines_added": commit["lines_added"],
                "lines_deleted": commit["lines_deleted"],
                "files_changed": [file_change["filename"] for file_change in commit["files_changed"]],
            }
            for commit in full_bundle["commits"]
        ]

    for field in fields:
        if field != "commits":
            bundle_data[field] = full_bundle[field]

    return json.dumps(bundle_data, indent=2, ensure_ascii=True)


def _compute_commit_facts(commits: list[dict]) -> str:
    """
    Precomputes objective facts about a dimension's commit list (active days,
    line counts, share of generic messages) instead of asking a small model
    to notice them unprompted while also composing a justification. Returns
    "" when there are no commits so callers can skip the section entirely.
    """
    if not commits:
        return ""

    authors = sorted({commit["author"] for commit in commits if commit.get("author")})
    active_days = sorted({commit["timestamp"][:10] for commit in commits if commit.get("timestamp")})

    lines_added_total = sum(commit.get("lines_added", 0) for commit in commits)
    lines_deleted_total = sum(commit.get("lines_deleted", 0) for commit in commits)

    # Recompute "meaningful" lines added by excluding files with a low-signal
    # extension, so bulk data/generated output doesn't masquerade as authored
    # code volume. Falls back to the aggregate total when a commit carries no
    # per-file breakdown.
    meaningful_lines_added = 0
    for commit in commits:
        files_changed = commit.get("files_changed") or []
        if not files_changed:
            meaningful_lines_added += commit.get("lines_added", 0)
            continue
        for filename in files_changed:
            if PurePosixPath(filename).suffix.lower() not in _LOW_SIGNAL_EXTENSIONS:
                # Per-file line counts aren't in the trimmed dimension bundle
                # (only filenames are), so distribute proportionally isn't
                # possible here — count the commit's lines once, keyed off
                # whether it touched ANY non-low-signal file.
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
    ]
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


def create_llm_client():
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
    raw_client = AsyncOpenAI( # Create an OpenAI-compatible client pointing at Ollama
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
        timeout=OLLAMA_TIMEOUT,
        http_client=transport, # Use the custom transport to capture requests and responses
    )

    client = instructor.from_openai( # Wrap OpenAI client with instructor to return Pydantic models instead of raw JSON
        raw_client, # The raw OpenAI-compatible client pointing at Ollama
        # Actually honor LLM_STRUCTURED_OUTPUT_MODE instead of always using
        # JSON mode -- JSON mode only describes the schema in the prompt, so
        # weak models can literally echo the schema back as their "answer"
        # instead of an instance of it. JSON_SCHEMA mode constrains Ollama's
        # decoding to the real schema and avoids that failure mode.
        mode=_INSTRUCTOR_MODES.get(_STRUCTURED_OUTPUT_MODE, instructor.Mode.JSON),
    )
    return client

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
    bundle_data = _dimension_bundle_data(bundle, dimension_name)
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

    computed_facts = (
        # Reuse the exact trimmed/filename-only commit list already built for
        # bundle_data (not bundle.commits directly, whose files_changed is a
        # list of FileDiff objects, not bare filenames).
        _compute_commit_facts(json.loads(bundle_data).get("commits", []))
        if "commits" in fields else ""
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