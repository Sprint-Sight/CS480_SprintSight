from __future__ import annotations

import logging
import os
import threading

import mlflow
from dotenv import load_dotenv
from mlflow import MlflowClient

load_dotenv()  # Load environment variables from .env file

log = logging.getLogger(__name__)

MLFLOW_TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI")

'''
Experiments are chosen per call by name
6 layers of LLMOps stack, but only 3 needed for our project:
1. Prompt Registry stores prompt templates and versions
2. Tracing & Observability captures LLM calls and responses for auditing and debugging
3. LLM Benchmarking evaluates LLM performance against known reference data and scoring rubrics (To be implemented via LLM judge in MLflow)
'''

_lock = threading.Lock()  # Ensure thread-safe initialization of MLflow tracking and prompt registry
_configured = False # Global variable to track if MLflow has been configured
_experiment_ids: dict[str, str] = {}  # Cache experiment IDs to avoid repeated lookups

def configure_mlflow() -> None: # Call this once per process to set up MLflow tracking and prompt registry
    global _configured
    with _lock: # Ensure thread-safe initialization
        if not _configured: # Only configure MLflow if it hasn't been configured yet
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI or "http://localhost:5000")
            log.info("MLflow tracking URI set to: %s", mlflow.get_tracking_uri())
            _configured = True

def get_experiment_id(experiment_name: str) -> str:
    configure_mlflow() # Ensure MLflow is configured before accessing experiments
    with _lock: # Ensure thread-safe access to experiment IDs
        if experiment_name in _experiment_ids: # Return cached experiment ID if available
            return _experiment_ids[experiment_name]
        client = MlflowClient()
        experiment = client.get_experiment_by_name(experiment_name) # Try to get the experiment
        if experiment is None: # If the experiment doesn't exist, create it
            try:
                experiment_id = client.create_experiment(experiment_name) # Create a new experiment
            except mlflow.exceptions.MlflowException: # Lost creation race with another process
                experiment = client.get_experiment_by_name(experiment_name) # Try to get the experiment again
                if experiment is None: # If it still doesn't exist, raise an error
                    raise RuntimeError(f"Failed to create or retrieve experiment '{experiment_name}'") from None
                experiment_id = experiment.experiment_id # Use the existing experiment ID
        else: # If the experiment exists, check if it's deleted
            if experiment.lifecycle_stage == "deleted": # If the experiment is deleted, raise an error
                raise RuntimeError(f"Experiment '{experiment_name}' is deleted")
            experiment_id = experiment.experiment_id # Use the existing experiment ID
        _experiment_ids[experiment_name] = experiment_id # Cache the experiment ID for future use
        return experiment_id

# Prompt registration lives in llmops/prompt_registry.py, which skips a template that is already
# the latest registered version. The old start_mlflow()/register_prompt() here registered a new
# version on every call and were removed with the startup prompt bootstrap.
