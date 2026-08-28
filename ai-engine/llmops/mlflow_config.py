from __future__ import annotations

import os, logging, mlflow
from mlflow.tracking import MlflowClient
from mlflow.entities import AssessmentSource
from mlflow.genai.scorers import Guidelines, ScorerSamplingConfig
from typing import Optional
from fastapi import FastAPI, Request, Query
from pydantic import BaseModel
from openai import OpenAI
from contextlib import contextmanager
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

log = logging.getLogger(__name__)

MLFLOW_TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI")
EXPERIMENT_NAME      = os.getenv("MLFLOW_EXPERIMENT_NAME")
BENCHMARK_EXPERIMENT = "sprintsight-benchmarks"

'''
6 layers of LLMOps stack, but only 3 needed for our project:
1. Prompt Registry stores prompt templates and versions
2. Tracing & Observability captures LLM calls and responses for auditing and debugging
3. LLM Benchmarking evaluates LLM performance against known reference data and scoring rubrics (To be implemented via LLM judge in MLflow)
'''

@mlflow.trace(name="Evaluate_Complete_Sprint")
def start_mlflow(experiment_name, name, template, commit_message, tags: Optional[dict] = None):
    # Call this once per process

    # 1. Setup tracking URI and experiment
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment(experiment_name)
    
    # 2. Enable automatic logging for LLM calls
    mlflow.openai.autolog()
    
    # 3. ONLY attempt prompt registration if an actual template was provided
    if name and template:
        register_prompt(
            name=name, 
            template=template, 
            commit_message=commit_message or "App Boot",
            tags = tags or {"author": "SprintSight"}
        )

def register_prompt(name, template, commit_message="Initial commit", tags: Optional[dict] = None):
    return mlflow.genai.register_prompt( # Register prompt version in MLflow Prompt Registry
        name=name,
        template=template,
        commit_message=commit_message,
        tags=tags or {"author": "SprintSight"}
    )