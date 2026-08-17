from __future__ import annotations

import os, logging, mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import AssessmentSource
from mlflow.genai.scorers import Guidelines, ScorerSamplingConfig
from typing import Optional
from fastapi import FastAPI, Request, Query
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

log = logging.getLogger(__name__)

MLFLOW_TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI")
EXPERIMENT_NAME      = os.getenv("MLFLOW_EXPERIMENT_NAME")
BENCHMARK_EXPERIMENT = "sprintsight-benchmarks"

'''
6 layers of LLMOps stack: 
1. MLflow Tracing — Auto-instrument any LLM framework in one line of code. Captures prompts, completions, tool calls, token usage, 
and latency for every request.
2. MLflow LLM Evaluation — Score outputs with LLM judges, custom scorers, and human feedback. Built-in judges for correctness, 
safety, groundedness, and RAG quality.
3. MLflow Prompt Registry — Version control, diff tracking, and aliases (dev, staging, production) for prompt templates. Edit 
in the UI without code changes.
4. MLflow AI Gateway — Single control plane for model access across providers with governance, rate limiting, authentication, 
fallback routing, and cost tracking.
5. MLflow Production Monitoring — Run LLM judges continuously against production traces to catch quality regressions before users 
report them.
6. MLflow Agent Server — Deploy agents to production with built-in tracing, streaming, and request validation.
'''

@mlflow.trace(name="Evaluate_Complete_Sprint")
def start_mlflow(name, template, commit_message, tags: Optional[dict] = None):
    # 1. Setup tracking URI and experiment
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment("SprintSight Evaluation")
    
    # 2. Enable automatic logging for LLM calls
    mlflow.openai.autolog()
    
    # 3. ONLY attempt prompt registration if an actual template was provided
    if template:
        register_prompt(
            name=name, 
            template=template, 
            commit_message=commit_message or "App Boot"
        )

def register_prompt(
    name: str, 
    template: str, # Required parameter
    commit_message: str = "Initial commit", 
    tags: dict = None
):
    """Registers a prompt version into MLflow Prompt Registry."""
    return mlflow.genai.register_prompt(
        name=name,
        template=template,
        commit_message=commit_message,
        tags=tags or {"author": "SprintSight"}
    )