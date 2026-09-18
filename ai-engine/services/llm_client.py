from __future__ import annotations
from schemas.rubrics_dimension_score import RubricDimensionScore
from schemas.sprint_assessment import SprintAssessment
from schemas.artifact_bundle import ArtifactBundle
from schemas.fixtures import high_performing_team, good_collab_low_output_team, imbalanced_high_output_team, lone_contributor_poor_outcome_team, struggling_team # Contains various teams
from openai import AsyncOpenAI
from uuid import uuid4
from services.audit_logger import write_audit_record
import contextvars, json, os, httpx, logging, instructor, time, mlflow
from mlflow.entities import SpanType
from llmops.prompt_registry import register_dimension_prompt, load_dimension_prompt, get_dimension_prompt, DIMENSION_PLACEHOLDERS

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
OLLAMA_TIMEOUT  = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))  # 5 min default

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

_audit_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "audit_context", default=None
)

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
        raw_client, # The raw OpenAI-compatible client pointing at Ollama
        mode=instructor.Mode.JSON, # ensures that the response is parsed as JSON, returned as a Pydantic model
    )
    return client

# Each child span of the parent span (Evaluate_Complete_Sprint)
@mlflow.trace(name="Evaluate_Dimension", span_type=SpanType.LLM)
async def evaluate_dimension(bundle: ArtifactBundle, dimension_name: str, model_name: str) -> RubricDimensionScore:
    # Asynchronously evaluates a single rubric dimension to ensure fast concurrent processing.
    # bundle_data = bundle.model_dump_json(indent=2) # json representation of the bundle for logging and debugging

    client = create_llm_client()  # Create a new client for this model
    
    audit_token = _audit_context.set(
        {
            "request_id": str(uuid4()),
            "team_id": bundle.team_id,
            "sprint_id": bundle.sprint_id,
            "dimension": dimension_name,
            "model": model_name,
        }
    )
    try: # The transport hooks capture the exact request and raw Ollama response.
        ## Prompt Registry by dimension
        loaded_prompt = load_dimension_prompt(dimension_name) # Load the prompt from MLflow Prompt Registry
        prev_template = get_dimension_prompt(dimension_name) # Get the prompt template
        if not loaded_prompt or loaded_prompt != prev_template: # If the prompt is not registered or has changed, register it
            register_dimension_prompt(dimension_name, model_name, bundle) # Register the prompt if not found
            loaded_prompt = load_dimension_prompt(dimension_name) # Load the prompt again
        placeholders = DIMENSION_PLACEHOLDERS[dimension_name]
        filled_prompt = loaded_prompt.format(
            # dimension=dimension_name,
            # assess=placeholders["assess"],
            # scoring=placeholders["scoring"],
            # output=placeholders["output"],
            bundle_data=_bundle_data_for_dimension(bundle, dimension_name),
        )

        print(f"Evaluating dimension '{dimension_name}' for team '{bundle.team_id}' using model '{model_name}'...") # Console message to track progress
        result = await client.chat.completions.create( # This method sends the prompt to Ollama
            model=model_name, # The Ollama model to use for evaluation
            response_model=RubricDimensionScore, # Parses the response into a Pydantic model
            messages=[{"role": "user", "content": filled_prompt}],
            max_retries=5,
        )
        return result.model_copy(update={"dimension": dimension_name}) # Ensures the dimension field is set correctly in the returned model
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