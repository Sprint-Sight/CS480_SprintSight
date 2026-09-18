from __future__ import annotations
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.sprint_assessment import SprintAssessment
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_feedback import SprintFeedback
from openai import AsyncOpenAI
import contextvars
import hashlib
import json
import os, httpx, logging, instructor, time
from uuid import uuid4
from services.audit_logger import write_audit_record
from services.grounding import find_ungrounded_citations
from prompts.templates import render_dimension_prompt, render_sprint_feedback_prompt
from schemas.modelname import MODEL_NUM_CTX

from dotenv import load_dotenv
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

_audit_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "audit_context", default=None
)


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
}


def _dimension_bundle_data(bundle: ArtifactBundle, dimension_name: str) -> str:
    fields = _DIMENSION_ARTIFACT_FIELDS.get(dimension_name)
    if fields is None:
        raise ValueError(f"Unknown rubric dimension: {dimension_name}")

    full_bundle = bundle.model_dump(mode="json")
    bundle_data = {
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


def _request_extra_body(model_name: str) -> dict:
    # Only override num_ctx for models we have a known Modelfile value for;
    # otherwise omit it so Ollama falls back to the model's own manifest value
    # instead of silently applying a single hardcoded number to every model.
    num_ctx = MODEL_NUM_CTX.get(model_name)
    if num_ctx is None:
        log.warning(
            "No known num_ctx for model '%s' — omitting it so Ollama uses the "
            "model's own manifest value instead of a guessed default.",
            model_name,
        )
        return {}
    return {"options": {"num_ctx": num_ctx}}


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

    instructor.Mode.JSON tells instructor to use JSON mode rather than
    OpenAI's tool-calling mode. JSON mode is more reliably supported
    across all Ollama models.
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
        raw_client,
        mode=instructor.Mode.JSON,
    )
    return client


async def evaluate_dimension(bundle: ArtifactBundle, dimension_name: str, model_name: str, dimention_prompt) -> RubricDimensionScore:
    # Asynchronously evaluates a single rubric dimension to ensure fast concurrent processing.
    bundle_data = _dimension_bundle_data(bundle, dimension_name)
    bundle_hash = hashlib.sha256(bundle_data.encode("utf-8")).hexdigest()

    approx_tokens = len(bundle_data) // 4
    log.info(
        ">>> Dimension '%s': bundle_data is %d chars (~%d tokens estimated)",
        dimension_name, len(bundle_data), approx_tokens,
    )

    prompt = render_dimension_prompt(dimension_name, dimention_prompt, bundle_data)

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
    try: # The transport hooks capture the exact request and raw Ollama response.
        result = await client.chat.completions.create(
            model=model_name,
            response_model=RubricDimensionScore,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_retries=3,
            extra_body=_request_extra_body(model_name),
        )
        if result.dimension != dimension_name:
            raise ValueError(
                f"Model returned dimension '{result.dimension}' while evaluating '{dimension_name}'."
            )
        # Drop only the fabricated/ungrounded citations rather than discarding
        # the whole dimension over a single bad citation, since the model
        # can't be forced to self-correct via validation_context on this
        # Instructor/OpenAI integration.
        ungrounded = find_ungrounded_citations(bundle_data, result.evidence_citations or [])
        if ungrounded:
            log.warning(
                "Dimension '%s': dropping %d ungrounded citation(s) rather than failing the whole dimension: %r",
                dimension_name, len(ungrounded), ungrounded,
            )
            write_audit_record(
                {
                    **(_audit_context.get() or {}),
                    "ungrounded_citations_dropped": ungrounded,
                }
            )
            result.evidence_citations = [
                citation for citation in (result.evidence_citations or [])
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
) -> SprintFeedback:
    """Generate strengths, weaknesses, and recommendations for the whole sprint."""
    scores_data = json.dumps(rubric_scores, indent=2, ensure_ascii=True, default=str)
    prompt = render_sprint_feedback_prompt(bundle.team_id, bundle.sprint_id, scores_data)
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
            extra_body=_request_extra_body(model_name),
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
    except Exception as e:
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
        async with httpx.AsyncClient(timeout=1800.0) as client:   # 30 min timeout
            async with client.stream("POST", pull_url, json={"name": model_name}) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        log.debug("Pull progress: %s", line)
        log.info("Model '%s' downloaded successfully.", model_name)
    except Exception as e:
        log.error("Failed to pull model '%s': %s", model_name, e)
        raise