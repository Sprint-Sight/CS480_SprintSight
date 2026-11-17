"""
api/main.py
 
The FastAPI application. This is the HTTP front door of your AI Assessment Service.
 
Endpoints:
    GET  /health          → Is the service up? Is Ollama reachable? Is the model ready?
    POST /assess/sprint/data → Submit ingested sprint data, receive a SprintAssessment
 
This file is intentionally thin. All real logic lives in services/evaluator.py.
"""

from __future__ import (
    annotations,  # Allows forward references in type hints (e.g., a function returning its own class type)
)

import logging
import os
from contextlib import (
    asynccontextmanager,  # Allows async context managers for startup/shutdown events
)

import instructor
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import assessment
from api.auth import service_token_configured
from evaluation.online.scheduler import start_judge_worker, stop_judge_worker
from llmops.mlflow_config import configure_mlflow
from llmops.prompt_registry import register_all_dimension_prompts
from services.llm_client import (
    check_ollama_health,
    create_llm_client,
)

load_dotenv()

'''
Creates FastAPI app
Lifespan hook calls setup_mlflow() before any request arrives
Registers router
'''
 
# Module-level variable that holds the Ollama client.
# Set during startup, used in every request.
_llm_client: instructor.AsyncInstructor | None = None

# Basic logging setup — logs go to stdout, Docker captures them
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

@asynccontextmanager # Allows us to define startup and shutdown logic for the FastAPI app
async def lifespan(app: FastAPI): # Initialise things that should exist for the app's entire lifetime
    try:
        # Only points the MLflow client at the tracking server; it registers nothing. The old
        # "sprint_assessment_prompt" bootstrap added a prompt version on every restart and
        # nothing ever read it. Real prompts are versioned by register_all_dimension_prompts().
        configure_mlflow()
    except Exception:
        log.exception("Failed to configure MLflow; tracking and prompt versioning may be unavailable.")

    try:
        # Versions every rubric dimension's live prompt in MLflow before any
        # grading request arrives. A registry outage here must not block
        # startup -- grading always renders prompts locally regardless.
        register_all_dimension_prompts()
    except Exception:
        log.exception("Failed to register dimension prompts in MLflow prompt registry.")

    global _llm_client
 
    log.info("AI Assessment Service starting up...")
    if not service_token_configured():
        log.warning(
            "AI_ENGINE_SERVICE_TOKEN is not set: /assess accepts requests from anyone who can "
            "reach this port. Set it (and the same value in the backend) outside a local demo."
        )
    log.info("Ollama URL: %s", os.getenv("OLLAMA_BASE_URL"))
 
    # Create the Ollama client once — reused across all requests
    _llm_client = create_llm_client()
 
    # The judge runs from a durable queue, not from request-scoped BackgroundTasks, so it
    # survives restarts. Jobs left running by a previous process are re-queued by the worker.
    try:
        start_judge_worker()
    except Exception:
        log.exception("Judge worker failed to start; assessments will be queued but not judged.")

    # Code before yield runs on startup
    yield # The application runs while paused here
    # Code after yield runs on shutdown, clear memory, close connections, etc.
    stop_judge_worker()

app = FastAPI(
    title="SprintSight",
    description="AI services for SprintSight, including LLM-based sprint assessment.",
    version="1.0.0",
    lifespan=lifespan
)

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request, exc: RequestValidationError):
    """Log and shape validation failures so the originating payload mismatch can be traced quickly."""
    log.error("Validation error on %s: %s", request.url.path, exc)
    log.error("Validation errors: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

app.include_router(assessment.router) # Register the assessment router with the FastAPI app

# Only the backend calls this API (server to server), so browsers need no cross-origin access by
# default. AI_ENGINE_CORS_ORIGINS (comma separated) opens specific origins, e.g. a local dashboard.
_CORS_ORIGINS = [o.strip() for o in os.getenv("AI_ENGINE_CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", summary="Health check")
async def health_check():
    """
    Returns service status and Ollama connectivity.
 
    Call this before running a demo to confirm:
    - The service is running
    - Ollama is reachable
    - The target model is downloaded and ready
 
    Response examples:
        200 OK:   {"status": "ok",    "ollama": {"status": "ok", "available": true}}
        200 OK:   {"status": "degraded", "ollama": {"status": "ok", "available": false}}
        503:      {"status": "error", "ollama": {"status": "error", "error": "..."}}
    """
    model_name = os.getenv("DEFAULT_MODEL_NAME", "sprintsight-qwen")
    ollama_status = await check_ollama_health(model_name)
 
    if ollama_status.get("status") == "error":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "error", "ollama": ollama_status},
        )
 
    if not ollama_status.get("available"):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "degraded",
                "message": "Model not yet downloaded. Pull it first.",
                "ollama": ollama_status,
            },
        )
 
    return {
        "status": "ok",
        "ollama": ollama_status,
    }

# Direct execution block
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)