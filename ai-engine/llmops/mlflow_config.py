from __future__ import annotations

import logging
import os

import mlflow
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

# @mlflow.trace(name="Evaluate_Complete_Sprint")
def start_mlflow(experiment_name, name: str | None = None,
                 template: str | None = None, commit_message: str | None = None,
                 tags: dict | None = None):
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

def register_prompt(name, template, commit_message="Initial commit", tags: dict | None = None):
    return mlflow.genai.register_prompt( # Register prompt version in MLflow Prompt Registry
        name=name, # Name/unique ID for the prompt
        template=template, # The actual prompt in itself
        commit_message=commit_message, # Commit message for this version of the prompt
        tags=tags or {"author": "SprintSight"}
    )

def format_prompt(name):
    loaded = mlflow.genai.get_prompt(name) # Load the prompt template from MLflow Prompt Registry
    prompt_filled = loaded.format()
    return prompt_filled
