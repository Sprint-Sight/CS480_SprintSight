# Real-sprint bundles for the model-comparison pipeline

Each `*.json` file in this directory is one dataset item for
`d_real_sprints`. File format: a JSON dump of
`schemas.artifact_bundle.ArtifactBundle.model_dump(mode="json")`.

The filename stem (`myfile.json` -> `myfile`) is the `example_id` used in
MLflow runs, plots, and judge-score merges. Pick stable names — a rename
produces a different dataset hash.

## Produced by

`backend/scripts/export_eval_bundles.py`. It builds each file the way a live
assessment builds its request (fresh commits from the project's repository,
the latest Jira snapshot, instructor expectations, uploaded documents and the
repository snapshot at HEAD), so the dataset is what production grades. Run it
inside the backend container; the exact commands are in the script's
docstring and `--help`. `--course CS203` exports every project and sprint as
`<team>_<sprint>.json`.

## Expected top-level JSON keys

```
team_id, sprint_id, commits, jira_tickets, peer_evaluations,
collaboration_metrics, artifact_metrics, project_context_documents,
repo_snapshot, instructor_expectations
```

`team_id` is the backend project id, as in a live assessment, so every
project gets its own. A missing field fails `ArtifactBundle.model_validate`
loudly, which is the point — a silent skip would quietly change the dataset
hash on the next run.
