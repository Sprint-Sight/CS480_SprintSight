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

DIMENSION_PLACEHOLDERS = {
    "requirements": {

        "first_sentence": '''Evaluate the individual's performance against the Requirements 
        dimension using the provided Jira/project data.''',

        "assess": '''
            Number and percentage of assigned Jira tickets marked Done
            Number of tickets remaining in To Do / In Progress / Blocked
            Total story points completed
            Whether any assigned tickets were abandoned or left stuck
            Overall delivery velocity relative to the assigned workload
            ''',

        "scoring": '''
            9–10: All assigned tickets are Done and a high number of story points were completed.
            6–8: Most tickets are Done, with no abandoned or stuck tickets.
            3–5: Less than half of tickets are Done and story-point velocity is low.
            1–2: Little or no progress; zero tickets are marked Done.''',

        "output": '''Provide the score, a concise justification, and the key evidence used. 
        Do not infer completion without supporting evidence.
        Provide the score, a concise justification, and the key evidence used. Do not infer completion without supporting evidence.
        ''',
    },

    "code_quality": {
        "first_sentence": '''Evaluate the individual's Code Quality based on the available Git 
        repository and commit history.''',

        "assess": '''
            Number and percentage of assigned Jira tickets marked Done
            Number of tickets remaining in To Do / In Progress / Blocked
            Total story points completed
            Whether any assigned tickets were abandoned or left stuck
            Overall delivery velocity relative to the assigned workload
            ''',

        "scoring": '''
            Volume of meaningful code contributions/lines added
            Number and consistency of code commits
            Whether commits represent substantive development work rather than trivial changes
            Clarity, specificity, and professionalism of commit messages
            Whether the commits demonstrate meaningful progress toward the project's requirements
            ''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the commit history. Distinguish between quantity of code and meaningful contribution.''',
    },

    "testing": {
        "first_sentence": '''Evaluate the individual's Testing performance using Jira tickets, 
        Git commits, test files, and other available testing evidence.''',

        "assess": '''
            Number of dedicated testing/test-related Jira tickets completed
            Presence of explicit test-related commits
            Evidence of unit, integration, system, or other appropriate tests
            Whether testing appears comprehensive relative to the code contributed
            Whether testing work is clearly attributable to the individual
            ''',

        "scoring": '''
            9–10: Comprehensive testing with clear evidence of unit, integration, and system tests.
            6–8: Adequate testing with some evidence of test coverage.
            3–5: Minimal testing with limited evidence of test coverage.
            1–2: No meaningful testing or test evidence is recorded.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the testing artifacts. Distinguish between quantity of tests and meaningful coverage.''',
    },

    "documentation": {
        "first_sentence": '''Evaluate the individual's Documentation performance using Jira tickets, 
        Git commits, and other available documentation evidence.''',

        "assess": '''
            Number of dedicated documentation-related Jira tickets completed
            Presence of explicit documentation-related commits
            Evidence of clear, concise, and comprehensive documentation
            Whether documentation appears comprehensive relative to the code contributed
            Whether documentation work is clearly attributable to the individual
            ''',

        "scoring": '''
            9–10: Comprehensive documentation with clear evidence of user guides, API docs, and inline comments.
            6–8: Adequate documentation with some evidence of coverage.
            3–5: Minimal documentation with limited evidence of coverage.
            1–2: No meaningful documentation or evidence is recorded.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the documentation artifacts. Distinguish between quantity of documentation and meaningful coverage.''',
    },

    "collaboration": {
        "first_sentence": '''Evaluate the individual's Collaboration performance using Jira tickets,
        Git commits, peer evaluations, and other available collaboration evidence.''',

        "assess": '''
            Number of peer evaluations completed and received
            Quality and constructiveness of peer feedback provided
            Evidence of active participation in team discussions and decision-making
            Willingness to assist teammates and contribute to shared goals
            Overall impact on team cohesion and productivity
            ''',

        "scoring": '''
            9–10: Exceptional collaboration with clear evidence of active participation and positive impact on the team.
            6–8: Good collaboration with some evidence of contribution.
            3–5: Minimal collaboration with limited evidence of contribution.
            1–2: No meaningful collaboration or evidence is recorded.''',

        "output": '''Provide the score, a concise justification, and the strongest evidence 
        from the collaboration artifacts. Distinguish between quantity of collaboration and meaningful impact.''',
    },
}

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
        raw_client,
        mode=instructor.Mode.JSON,
    )
    return client

# Each child span of the parent span (Evaluate_Complete_Sprint)
@mlflow.trace(name="Evaluate_Dimension", span_type=SpanType.LLM)
async def evaluate_dimension(bundle: ArtifactBundle, dimension_name: str, model_name: str, dimension_prompt) -> RubricDimensionScore:
    # Asynchronously evaluates a single rubric dimension to ensure fast concurrent processing.
    bundle_data = bundle.model_dump_json(indent=2)

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
        prompt = mlflow.genai.register_prompt( # Register prompt in MLflow Prompt Registry for versioning and tracking
            name=f"Evaluate_{dimension_name}",
            template=dimension_prompt,
            commit_message=f"Prompt for dimension '{dimension_name}' evaluation",
            tags={"dimension": dimension_name, "model": model_name, "team_id": bundle.team_id, 
                    "sprint_id": bundle.sprint_id, "author": "SprintSight"}
        )
        prompt_alias = "production" # Production default for now
        mlflow.genai.set_prompt_alias(f"Evaluate_{dimension_name}", prompt_alias, prompt.version) # Set alias for the prompt version
        loaded = mlflow.genai.load_prompt(f"prompts:/Evaluate_{dimension_name}@{prompt_alias}") # Load the prompt template from MLflow Prompt Registry
        filled_prompt = loaded.format(
            dimension=dimension_name,
            assess=DIMENSION_PLACEHOLDERS[dimension_name]["assess"],
            scoring=DIMENSION_PLACEHOLDERS[dimension_name]["scoring"],
            output=DIMENSION_PLACEHOLDERS[dimension_name]["output"]
        )

        print(f"Evaluating dimension '{dimension_name}' for team '{bundle.team_id}' using model '{model_name}'...") # Console message to track progress
        return await client.chat.completions.create( # This method sends the prompt to Ollama
            model=model_name,
            response_model=RubricDimensionScore, # Parses the response into a Pydantic model
            messages=[{"role": "user", "content": filled_prompt}],
            max_retries=5,
        )
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