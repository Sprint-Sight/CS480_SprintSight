# Real-sprint bundles for the model-comparison pipeline

Each `*.json` file in this directory is one dataset item for
`d_real_sprints`. File format: a JSON dump of
`schemas.artifact_bundle.ArtifactBundle.model_dump(mode="json")`.

The filename stem (`myfile.json` -> `myfile`) is the `example_id` used in
MLflow runs, plots, and judge-score merges. Pick stable names — a rename
produces a different dataset hash.

## Produced by

`backend/scripts/export_eval_bundles.py`, which queries the SprintSight
backend's Postgres via the same repository classes the API uses. See
that script's `--help` for the exact invocation.

## Expected top-level JSON keys

```
team_id, sprint_id, commits, jira_tickets, peer_evaluations,
collaboration_metrics, artifact_metrics, project_context_documents,
instructor_expectations
```

A missing field fails `ArtifactBundle.model_validate` loudly, which is
the point — a silent skip would quietly change the dataset hash on the
next run.
