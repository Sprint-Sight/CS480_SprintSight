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
from llmops.mlflow_config import start_mlflow
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
    start_mlflow(
        experiment_name="Sprintsight evaluation",
        name="sprint_assessment_prompt", 
        template="""\
You are an expert agile coach evaluating team performance.
Analyze the following sprint bundle and output a score:
{{ bundle_data }}
""", 
        commit_message="Initial prompt bootstrap"
    )

    try:
        # Versions every rubric dimension's live prompt in MLflow before any
        # grading request arrives. A registry outage here must not block
        # startup -- grading always renders prompts locally regardless.
        register_all_dimension_prompts()
    except Exception:
        log.exception("Failed to register dimension prompts in MLflow prompt registry.")

    global _llm_client
 
    log.info("AI Assessment Service starting up...")
    log.info("Ollama URL: %s", os.getenv("OLLAMA_BASE_URL"))
 
    # Create the Ollama client once — reused across all requests
    _llm_client = create_llm_client()
 
    # # Attempt to pull the model if not already downloaded.
    # # This blocks startup until the model is ready.
    # # On first run this may take several minutes — that is expected.
    # try:
    #     await pull_model_if_missing()
    #     log.info("Model is ready.")
    # except Exception as e:
    #     log.error(
    #         "Could not ensure model  is available: %s. "
    #         "The service will start but assessments may fail until "
    #         "the model is manually pulled.",
    #         e
    #     )
    
    # 2. Setup your global LLM client here if desired (or rely on llm_client.py)
    # _llm_client = create_llm_client(model_name)
    
    # Code before yield runs on startup
    yield # The application runs while paused here
    # Code after yield runs on shutdown, clear memory, close connections, etc.

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

app.add_middleware( # CORS middleware to allow cross-origin requests from any local port
    CORSMiddleware,
    allow_origins=["*"], # Allows calls from any local ports, LATER CHANGE TO DATA AND/OR FRONTEND ORIGIN only
    allow_credentials=True,
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)