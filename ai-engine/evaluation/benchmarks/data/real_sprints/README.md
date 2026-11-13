# Real-sprint bundles for the model-comparison pipeline

Each `*.json` file in this directory is one dataset item for
`d_real_sprints`. File format: a JSON dump of
`schemas.artifact_bundle.ArtifactBundle.model_dump(mode="json")`.

The filename stem (`myfile.json` -> `myfile`) is the `example_id` used in
MLflow runs, plots, and judge-score merges. Pick stable names — a rename
produces a different dataset hash.

The bundles are **not committed**: they hold students' names, commit
messages, Jira tickets and source files. Export them locally (below); the
`.json` files stay on your machine. `evaluation/offline/RUNBOOK.md` ("Build the
real-sprint dataset") has the full procedure.

## Produced by

`backend/scripts/export_eval_bundles.py`. It builds each file the way a live
assessment builds its request (fresh commits from the project's repository,
the latest Jira snapshot, instructor expectations, uploaded documents and the
repository snapshot at HEAD), so the dataset is what production grades. Run it
inside the backend container; the exact commands are in the script's
docstring and `--help`. `--course <course_id_or_code>` exports every project
and sprint as `<team>_<sprint>.json`.

## How to export locally

With the backend container (`sprintsight-backend`) running, execute from the
repository root:

```bash
# Required on Windows Git Bash (MINGW64) to prevent POSIX path translation
export MSYS_NO_PATHCONV=1

# 1. Copy the export script into the running backend container
docker cp backend/scripts/export_eval_bundles.py sprintsight-backend:/tmp/export_eval_bundles.py

# 2. Export bundles inside the container (pass the exact course UUID if multiple CS203 terms exist)
docker exec -e PYTHONPATH=/app -w /app sprintsight-backend \
    python /tmp/export_eval_bundles.py \
    --course c12715cc-4004-443f-965e-c2db1e708d2e \
    --out /tmp/real_sprints \
    --overwrite

# 3. Copy the generated JSON bundles into this directory
docker cp sprintsight-backend:/tmp/real_sprints/. ai-engine/evaluation/benchmarks/data/real_sprints/