from __future__ import annotations

import logging, os, mlflow, threading
from contextlib import contextmanager
from typing import Iterator
from mlflow import MlflowClient
from mlflow.entities import SpanType
from mlflow.entities.trace_location import MlflowExperimentLocation
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

log = logging.getLogger(__name__)

MLFLOW_TRACKING_URI  = os.getenv("MLFLOW_TRACKING_URI")
EXPERIMENT_NAME      = os.getenv("MLFLOW_EXPERIMENT_NAME")
BENCHMARK_EXPERIMENT = "sprintsight-benchmarks"

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

def configure_mlflow(): # Call this once per process to set up MLflow tracking and prompt registry
    global _configured
    with _lock: # Ensure thread-safe initialization
        if not _configured: # Only configure MLflow if it hasn't been configured yet
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI or "http://localhost:5000")
            log.info("MLflow tracking URI set to: %s", mlflow.get_tracking_uri())
            _configured = True

def get_experiment_id(experiment_name: str): 
    configure_mlflow() # Ensure MLflow is configured before accessing experiments
    with _lock: # Ensure thread-safe access to experiment IDs
        if experiment_name in _experiment_ids: # Return cached experiment ID if available
            return _experiment_ids[experiment_name]
        client = MlflowClient()
        experiment = client.get_experiment_by_name(experiment_name) # Try to get the experiment
        if experiment is None: # If the experiment doesn't exist, create it
            try:
                experiment_id = client.create_experiment(experiment_name) # Create a new experiment
            except mlflow.exceptions.MlfowException: # Lost creation race with another process
                experience = client.get_experiment_by_name(experiment_name) # Try to get the experiment again
                if experience is None: # If it still doesn't exist, raise an error
                    raise RuntimeError(f"Failed to create or retrieve experiment '{experiment_name}'")
                experiment_id = experience.experiment_id # Use the existing experiment ID
        else: # If the experiment exists, check if it's deleted
            if experiment.lifecycle_stage == "deleted": # If the experiment is deleted, raise an error
                raise RuntimeError(f"Experiment '{experiment_name}' is deleted")
            experiment_id = experiment.experiment_id # Use the existing experiment ID
        _experiment_ids[experiment_name] = experiment_id # Cache the experiment ID for future use
        return experiment_id

@contextmanager # Context manager to create a new MLflow run within an experiment
def experiment_run(experiment_name, run_name, root_span_name, *, tags: dict[str, str] | None = None, span_type: str = SpanType.CHAIN) -> Iterator[mlflow.ActiveRun]:

    experiment_id = get_experiment_id(experiment_name) # Get the experiment ID for the given name
    client = MlflowClient()
    parent = mlflow.active_run() # Get the current active run to set as parent
    if parent is not None: # If there is a parent run, set it as the
        tags["mlflow.parentRunId"] = parent.info.run_id # Set the parent run ID in the tags
    
    run_id = client.create_run(experiment_id, run_name=run_name, tags=tags or {}).info.run_id # Create a new run in the experiment
    status = "FINISHED"
    try:
        with mlflow.start_span(name=root_span_name, run_id=run_id, span_type=span_type,
                               trace_destination=MlflowExperimentLocation(experiment_id)) as span: # Start a new span for tracing
            yield mlflow.active_run() # Yield the active run to the caller
    except BaseException as e: # If an exception occurs, mark the run as failed
        status = "FAILED"
        client.set_tag(run_id, "mlflow.runStatus", f"{type(e).__name__}: {e}"[:250]) # Set the run status to FAILED
        raise
    finally:
        client.set_terminated(run_id, status=status) # Terminate the run with the appropriate status


def start_mlflow(experiment_name, name: str | None = None,
                 template: str | None = None, commit_message: str | None = None,
                 tags: dict | None = None):
    configure_mlflow() # Ensure MLflow is configured before starting a run
    if name and template: # If a prompt name and template are provided, register the prompt
        register_prompt(name, template, commit_message=commit_message or "Initial commit", tags=tags or {"author": "SprintSight"})

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