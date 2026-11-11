"""Every MLflow experiment name the engine and its evaluation tools use, in one place.

The values are the strings each caller used before they were gathered here, so new runs keep
landing next to the old ones. Change a name here only when you mean to start a new experiment.

Not listed:
  * The per-run experiment names of research/trials/run_cs203_trial.py and run_fixture_trial.py.
    Those are scratch defaults, changed for every trial run (`--experiment-name`).
  * MLFLOW_EXPERIMENT_NAME (set in docker-compose.yaml). No SprintSight code reads it, but
    MLflow's fluent API does: it is the experiment a run starts in when nothing set one.
"""

# Production grading: default `experiment_name` query parameter of POST /assess/sprint/data.
# Assessment runs, their traces and the judge runs for those traces all live here.
PRODUCTION = "SprintSight Evaluations"

# Passed to start_mlflow() at application startup. start_mlflow() registers the bootstrap
# prompt only and does not set the experiment (it is process-global, see run_tracking.py).
STARTUP = "Sprintsight evaluation"

# evaluation/offline: model-comparison runs (runner, cli run/analyze).
MODEL_COMPARISON = "sprintsight-model-comparison"

# evaluation/offline/judge_study/. SPRINTSIGHT_JUDGE_EXPERIMENT overrides it.
JUDGE_STUDY = "sprintsight-judge-eval"

# research/gpu/report.py --mlflow: GPU utilisation summaries.
GPU_UTILISATION = "sprintsight_gpu_utilisation"

# research/trials/validation_harness.py.
VALIDATION_HARNESS = "SprintSight-Research"
