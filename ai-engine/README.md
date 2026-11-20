# SprintSight AI Engine

> Updated: 20 November, 2026

SprintSight's AI engine is a local FastAPI service that evaluates ingested
sprint artifact bundles with an Ollama model. It uses the OpenAI-compatible
Ollama API and Instructor's Pydantic response validation; no student data is
sent to a cloud LLM.

**Contents:**
[Current status](#current-status) ·
[Architecture](#architecture) ·
[Layout](#layout) ·
[Setup](#setup) ·
[API](#api) ·
[Evaluation flow](#evaluation-flow) ·
[Configuration](#configuration) ·
[MLflow in SprintSight](#mlflow-in-sprintsight) ·
[Running on the GPU cluster](#running-on-the-gpu-cluster)

## Current Status

- The HTTP API evaluates sprint data ingested by the backend from Git, Jira,
  and uploaded documents.
- Six rubric dimensions are scored: `code_quality`, `testing`,
  `documentation`, `requirements`, `collaboration`, and `cicd`.
- Dimension evaluations are bounded by `LLM_DIMENSION_CONCURRENCY` (default `1`,
  so one Ollama call is in flight at a time on the single model slot).
- A dimension that fails after retries is filled with a placeholder score
  (`evaluation_failed: true`) so every dimension is always present in the
  response. The placeholder is **not** a score: it is left out of
  `overall_score`, carries a `failure_class` (`timeout`, `infra_unavailable`,
  `schema_validation`, `output_length`, `context_truncated`) and the full error
  in `error_detail`, and the backend excludes it from the team score and flags
  the report for manual review.
- The evaluator returns a float `overall_score` (average of the scored
  dimensions, rounded to 2 decimal places) — not rounded to an integer, since the backend
  multiplies it by 10 for its /100 team score and integer rounding here would
  collapse that /100 score down to multiples of 10.
- `member_contributions` is currently returned as its default empty list; the
  evaluator does not generate individual contribution scores yet.
- Each Ollama request and raw response is written to a text audit record,
  including failed requests.
- MLflow records a trace for every assessment, versions each prompt in the
  prompt registry, and stores the citation judge's verdicts. The judge runs
  from a durable queue after grading. The SprintSight backend reads those
  traces and writes instructor feedback back (see
  [MLflow in SprintSight](#mlflow-in-sprintsight)).

## Architecture

The engine does three separate jobs. Grading answers requests; judging and review run
behind it; benchmarking is offline research that uses the same grading code.

### 1. Grading (online, one request per sprint)

```text
Backend
  | POST /assess/sprint/data?modelname=...
  v
FastAPI (main.py, port 8001)
  v
api/assessment.py            validates the payload, builds an ArtifactBundle
  v
services/evaluator.py        evaluates the six rubric dimensions (bounded concurrency)
  |--> llmops/prompt_registry.py   versions each prompt in MLflow; the version used is
  |                                tagged on the trace (prompt.Evaluate_<dimension>)
  '--> services/llm_client.py      Instructor + OpenAI client
        v
      Ollama (port 11434)
  v
SprintAssessment  (+ trace_id, experiment_name)  --> back to the backend
  '--> trace queued for the judge; a trace with a failed dimension is also
       tagged "Flagged for review" and added to the review queue
```

### 2. Judging and review (online, after the response is sent)

```text
Judge queue (SQLite, data/judge_jobs.sqlite3)
  v
evaluation/online/scheduler.py     worker: runs only while no grading call holds the model slot
  v
evaluation/online/run_judges.py    citation-grounding and narrative judges (sprintsight-judge-phi);
  |                                results are written as assessments on the same trace
  |--> evaluation/judges/flagging.py   fixed thresholds decide whether the trace needs review
  |       v
  |     llmops/review_queue.py         flagged traces join the shared "flagged_runs" queue
  '--> evaluation/online/promote.py    promotion gate: may move a prompt's `production` alias
```

### 3. Benchmarking (offline, research)

```text
evaluation/benchmarks/         bundles with gold assessments (synthetic, CS203, real sprints)
  v
evaluation/offline/runner.py   one run = one model x dataset x prompt x seed, graded by the same
  |                            services/ code; per-example rows and metrics logged to MLflow
  v
evaluation/offline/analysis.py, plots.py   comparison tables and paired-bootstrap confidence
                                           intervals (evaluation/stats.py)
evaluation/offline/judge_study/   checks the judge itself against human and gold scores
```

Commands, in order, are in `evaluation/offline/RUNBOOK.md`.

### What MLflow and PostgreSQL hold

```text
MLflow (127.0.0.1:5000)   traces, runs, the prompt registry, judge assessments, review queues
  |                       experiments: SprintSight Evaluations (production grading and judging),
  |                       sprintsight-model-comparison (benchmark sweeps),
  |                       sprintsight-judge-eval (judge study)
  v
PostgreSQL (port 5432)    MLflow's backend store; run artifacts are in the mlflow_artifacts volume
```

The backend (not this service) reads traces by trace ID and writes instructor feedback to
MLflow as HUMAN assessments.

## Layout

```text
ai-engine/
├── main.py, api/          FastAPI app, lifespan setup and the assessment route
├── services/              grading: evaluator, LLM client, evidence packing, grounding, audit logs
├── prompts/               rubric criteria and prompt templates
├── schemas/               API and domain models
├── llmops/                MLflow: tracking setup, experiment names, prompt registry, review queue
├── evaluation/            everything that measures grading quality
│   ├── judges/            citation-grounding judge, verdict metadata, grade scorer, flagging
│   ├── online/            production judging: durable queue, worker, judge run, prompt promotion
│   ├── benchmarks/        benchmark bundles + gold (synthetic v1/v2, CS203, real sprints)
│   ├── offline/           model-comparison pipeline, judge study, judge canary (RUNBOOK.md)
│   └── stats.py           paired bootstrap shared by promotion and analysis
├── mlflow-server/         Dockerfile for the MLflow server (pinned version + Postgres driver)
├── hpc/                   Ollama on the Origami Slurm GPU cluster (README.md)
├── models/                Ollama Modelfiles
├── research/              experiment scratchpad: GPU benchmarks, trials (README.md)
├── tests/                 pytest suite
├── docker-compose.yaml    Ollama, model init, FastAPI, MLflow and PostgreSQL
├── Dockerfile, Makefile   engine image and local shortcuts
├── requirements.txt       pinned dependencies (mlflow must match the server image)
└── pyproject.toml         tool configuration
```

Folders that hold data produced by running the engine, not source code:

| Folder | Contents | In git? |
|---|---|---|
| `audit_logs/` | One text record per LLM request and response | no (mounted into the container) |
| `data/` | `judge_jobs.sqlite3`, the durable judge queue | no |
| `repo/` | Local clones used by fixture bundles and trials | no |
| `res/`, `results/` | Raw judge-study results (`*.jsonl`) | `results/` yes, `res/` no |
| `mlruns/`, `mlflow.db` | Leftovers from running MLflow outside Docker; the server now uses Postgres | ignored |

Nothing under `services/`, `api/` or `evaluation/` imports `research/`.

## Setup

Run Docker commands from this directory:

```powershell
cd ai-engine

# Start Ollama, MLflow, and PostgreSQL
docker compose up -d db ollama mlflow_service

# Build and start the FastAPI service
docker compose up -d --build --force-recreate sprintsight_ai

# Check service status
docker compose ps
```

The services are available at:

| Service | URL |
|---|---|
| FastAPI | `http://localhost:8001` |
| Swagger UI | `http://localhost:8001/docs` |
| MLflow | `http://localhost:5000` |
| Ollama | `http://localhost:11434` |

### Custom Ollama models are created by a one-shot Compose initializer

The compose file now contains a lightweight `model-init` service that waits for
Ollama to be reachable and only creates the SprintSight aliases when they are
missing:

- `sprintsight-qwen` from `models/Modelfile.qwen`
- `sprintsight-mistral` from `models/Modelfile.mistral`
- `sprintsight-gemma` from `models/Modelfile.gemma`
- `sprintsight-judge-phi` from `models/Modelfile.phi`

This means repeated `docker compose up` runs are mostly idempotent because the
initializer checks `ollama list` for the target model aliases and skips the
`pull`/`create` work when the aliases already exist.

You can still verify the installed models with:

```powershell
docker compose exec ollama ollama list
```

The default model is `sprintsight-qwen`. Override it with
`DEFAULT_MODEL_NAME` in `.env` or the compose environment.

## API

The AI engine accepts the backend canonical payload route:

```http
POST /assess/sprint/data?modelname=sprintsight-qwen
Content-Type: application/json
```

with a JSON body shaped as:

```json
{
  "sprint_context": {
    "course_id": "CS101",
    "project_id": "<project_id>",
    "sprint_id": "Sprint-1",
    "captured_at": "2026-09-10T00:00:00Z"
  },
  "collaboration_metrics": {
    "commit_frequency": 3.5,
    "code_churn": 42,
    "pr_turnaround_hours": 12,
    "assigned_story_points": 10,
    "completion_percent": 80
  },
  "commits": [],
  "jira_tickets": [],
  "peer_evaluations": [],
  "artifact_metrics": {},
  "instructor_expectations": "No instructor guidance provided."
}
```

The backend worker emits the assessment job progress through the backend SSE endpoint `GET /api/v1/assessments/jobs/{job_id}/events`.

### Health check

```powershell
curl.exe http://localhost:8001/health
```

The endpoint checks whether Ollama is reachable and whether the configured
default model is available. It returns `200` with `status: "ok"` when ready,
`200` with `status: "degraded"` when Ollama is reachable but the model is
missing, and `503` when Ollama cannot be reached.

### Assess ingested sprint data

The endpoint returns a `SprintAssessment` containing:

- `overall_score`: float average from 0 to 10, rounded to 2 decimal places
- `rubric_scores`: one `RubricDimensionScore` for each of the 6 dimensions —
  always present; if a dimension's evaluation failed after retries, it is
  filled with a conservative placeholder score and `evaluation_failed: true`
  instead of being omitted
- `failed_dimensions`: computed list of dimensions that could not be scored
  (i.e. flagged with `evaluation_failed: true`), and `evaluation_failed`: true
  when that list is not empty
- `trace_id`: the MLflow trace of this grading run. The judge runs after the
  response is sent, so this is the key the backend stores to join a report to
  its judge verdict
- `experiment_name`: the MLflow experiment that trace belongs to (the
  `experiment_name` query parameter; default `SprintSight Evaluations`)
- `executive_summary`: deterministic summary based on the average
- `key_recommendations`: currently contains that summary
- `member_contributions`: currently empty because it is not generated by the
  evaluator

## Evaluation flow

### Grading (per request)

1. The backend ingests Git, Jira, and document data and sends the canonical
  payload to `api/assessment.py`.
2. `api/assessment.py` validates the payload and builds an `ArtifactBundle`.
3. `services/evaluator.py` registers the prompts (see *Prompt registry* below),
   then starts one task per rubric dimension.
4. `services/llm_client.py` builds each dimension's prompt: computed facts
   over ALL commits, then `services/evidence_packer.py` fills the token
   budget with the evidence that dimension needs (see below).
5. Instructor validates the response as `RubricDimensionScore`, retrying up to
   three times for a dimension-level failure. `services/grounding.py` then
   resolves every citation against the evidence the model was shown: it
   keeps exact file/line anchors, clamps ranges to the lines shown,
   downgrades unseen line numbers to file level, and drops anything else.
6. The evaluator collects successful dimensions, calculates their average, and
   builds `SprintAssessment`. If any dimension failed, the trace is tagged
   `Flagged for review` and added to the review queue.
7. MLflow records the trace and the average score. The HTTP client hooks write
   request/response audit files under `audit_logs/`.
8. The response carries `trace_id` and `experiment_name`, and the trace is put on
   the judge queue. Judging never delays the response.

### Prompt registry

Each grading run starts by registering the seven prompts (six `Evaluate_<dimension>` and
`Generate_Sprint_Feedback`) with `llmops/prompt_registry.py`:

1. The current template is compared with every stored version. If one matches, it is reused,
   so repeated assessments never create duplicate versions.
2. A template that changed becomes a new version with the `challenger` alias.
3. The version used for each prompt is stored on the trace (`prompt.<name>` tags and the root
   span's `prompt_versions`), so any grade can be traced to its exact prompt text.

Grading always renders the prompt text from `prompts/dimension_criteria.py`; the registry records
versions but does not choose them. In production grading the `production` alias is moved only by
the promotion gate (step 5 below); research scripts can also set aliases.

### Judging and review (after the response)

1. A worker takes the trace from the judge queue when no grading call is using the Ollama model
   slot, and runs the citation-grounding and narrative judges on it
   (`evaluation/online/run_judges.py`). Each result is an assessment on that same trace;
   the citation verdicts are also attached as structured metadata.
2. `evaluation/judges/flagging.py` checks the results against fixed thresholds: hallucination rate
   above 0.10, severity-weighted error above 0.15, fewer than 10 judged citations, grounded rate
   below 0.50, any fabricated citation removed by code, a narrative or justification
   contradiction, or a judge that produced no output.
3. A trace with at least one production reason is added to the shared `flagged_runs` review
   queue (`llmops/review_queue.py`). Reasons from the gold-score comparison are research-only and
   are logged without queueing unless `JUDGE_QUEUE_RESEARCH_FLAGS=1`. Queueing never breaks
   grading or judging: a failure is logged and the run carries on.
4. The backend reads the judge results and flags by trace ID and shows them to instructors
   (Insights, "Needs attention"). Instructors do not use the MLflow queue.
5. For each dimension, `evaluation/online/promote.py` decides whether the prompt version used may
   become `production`: it must pass absolute gates (at least 3 judged citations, hallucination
   and severity-weighted error within the thresholds). With no production version yet it is
   promoted; otherwise it must beat production on at least 3 shared gold-scored inputs with a
   mean error gain of at least 0.2 and a bootstrap interval that excludes zero. Real course
   data has no gold scores, so in practice only the first promotion happens there.

### Benchmarking (offline, on demand)

Benchmarking compares models and prompts on fixed inputs with known answers. It reuses the grading
code, so a result reflects what production would do.

1. `evaluation/benchmarks/` supplies datasets of bundles with gold assessments (`d1_fixtures`,
   `d_real_sprints`; list them with `python -m evaluation.offline.cli list-datasets`).
2. `python -m evaluation.offline.cli run` grades the dataset for ONE condition (model x dataset x
   prompt x seed) and logs it as one MLflow run in `sprintsight-model-comparison`, with a
   per-example row for each input.
3. The judge pass scores those assessments, and `judge_study/` checks the judge against human
   and gold scores before its numbers are trusted.
4. `python -m evaluation.offline.cli analyze` collects the runs and writes comparison tables and
   plots, using paired bootstrap confidence intervals (`evaluation/stats.py`) so a gap between
   two models is reported with its uncertainty.
5. The same gold-scored runs are what the promotion gate in step 5 above compares prompt
   versions on.

The full command order is in `evaluation/offline/RUNBOOK.md`; the judge study is described in
`evaluation/offline/README.md`.

## Evidence packing

The backend sends, besides commits and Jira data, per-file diffs (captured at
ingestion) and `repo_snapshot`: every tracked file at the submitted HEAD.
For each dimension the packer renders, within
`min(num_ctx, LLM_EVIDENCE_CONTEXT_CAP)` minus the prompt scaffold and the
answer reserve:

| Section | What | Dimensions |
|---|---|---|
| Fixed inputs | Instructor expectations, Jira tickets (one JSON per line), metrics | per `_DIMENSION_ARTIFACT_FIELDS` |
| Commit ledger | One line per commit for the whole history; shorter format, then most-relevant subset, only if it cannot fit | all except requirements |
| File tree | Every file at HEAD with line counts | code_quality, testing, documentation, cicd |
| HEAD contents | Line-numbered files of the dimension's category, ranked by churn and spread across modules | same |
| Code outline | Definition/test-name lines of files not shown in full | code_quality, testing |
| Diff excerpts | New-file line-numbered hunks, round-robin across authors | code_quality, testing, documentation, cicd |

Every file and diff block carries a `cite as path:Lx-Ly[@sha7]` anchor, and the
resolved citation (kind, file_path, line_start, line_end, commit_sha) is
returned in `evidence_citations`. Inspect what any dataset example would send
with `python -m evaluation.offline.inspect_bundle --example <id>`.

## Audit records

Audit files are written to `audit_logs/` and mounted into the container at
`/app/audit_logs`. Each record includes the team, sprint, model, dimension,
request payload, raw Ollama response, HTTP status, duration, and client error
when applicable. The directory is retained on the host across container
restarts.

## Validation harness

The research harness compares the local models against the fixture set for
structural validity, discriminative validity, reliability, and cross-model
agreement. It writes raw runs and an aggregated summary to
`research/validation_results/`.

Smoke-test one model first:

```powershell
docker compose exec sprintsight_ai python -m research.trials.validation_harness `
    --models sprintsight-qwen --repeats 1
```

Run a broader comparison:

```powershell
docker compose exec sprintsight_ai python -m research.trials.validation_harness `
    --models sprintsight-qwen sprintsight-mistral sprintsight-gemma `
    --repeats 5
```

Each fixture/model/repeat evaluates six dimensions, so larger runs can take
considerable time on local hardware.

## Useful files

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app, lifespan setup, and `/health` |
| `api/assessment.py` | Assessment route, query enums, and fixture selection |
| `services/evaluator.py` | Dimension orchestration and score aggregation |
| `services/llm_client.py` | Ollama client, structured output, retries, and health checks |
| `services/audit_logger.py` | Human-readable LLM request/response records |
| `prompts/dimension_criteria.py`, `prompts/templates.py` | Rubric dimensions and grading prompts |
| `llmops/mlflow_config.py`, `llmops/run_tracking.py` | MLflow tracking setup and concurrency-safe runs |
| `llmops/experiments.py` | Every MLflow experiment name |
| `llmops/prompt_registry.py` | Prompt versions and the production/challenger aliases |
| `evaluation/online/scheduler.py`, `job_queue.py` | Durable judge queue and the worker that keeps judging away from grading |
| `evaluation/judges/citation_grounding.py` | LLM judge that checks each citation against the evidence |
| `evaluation/judges/verdict_metadata.py` | Structured citation verdicts attached to the judge's assessment |
| `evaluation/judges/flagging.py` | Thresholds that decide which traces are flagged for review |
| `evaluation/online/promote.py` | Promotion gate: moves the `production` prompt alias when a challenger beats it |
| `llmops/review_queue.py` | The shared `flagged_runs` MLflow review queue |
| `mlflow-server/Dockerfile` | MLflow server pinned to the client version, with the Postgres driver |
| `evaluation/benchmarks/` | Benchmark bundles and gold assessments (synthetic v1/v2, CS203, real sprints) |
| `evaluation/offline/RUNBOOK.md` | Model comparison and judge-study commands, in order |
| `research/README.md` | GPU benchmark, figure and trial scripts |
| `docker-compose.yaml` | Ollama, model init, FastAPI, MLflow, and PostgreSQL services |

**Which prompt grades?** Grading uses the prompt text in `prompts/dimension_criteria.py`. Each new
text is registered as the `challenger` alias, and its version is stored on the trace
(`prompt.Evaluate_<dimension>`). The `production` alias is only the promotion gate's research
baseline: `evaluation/online/promote.py` and `research/trials/*` read it, the grading API does not.
The gate needs 3+ shared inputs with gold scores, so on real course data it does not promote.

**Review queues.** Flagged traces go to one shared custom queue named `flagged_runs` per experiment
(`llmops/review_queue.py`), for admin and research use only. Instructors review flagged runs from the
SprintSight Insights page ("Needs attention"), never from the MLflow UI, which shows raw prompts.

## Configuration

The main environment variables are:

```text
MLFLOW_DISABLE_TELEMETRY=true                 # set in docker-compose.yaml for the app and the MLflow server
SPRINTSIGHT_ALLOW_REMOTE_JUDGE=0              # 1 allows the hosted fixture judge (research only); keeps production local
LLM_DIMENSION_CONCURRENCY=1                   # dimension calls in flight at once
SPRINTSIGHT_AI_OLLAMA_URL=http://ollama:11434/v1   # container's OLLAMA_BASE_URL; set in .env (HPC: host.docker.internal)
OLLAMA_TIMEOUT_SECONDS=300
DEFAULT_MODEL_NAME=sprintsight-qwen
# MLFLOW_TRACKING_URI is fixed to http://mlflow_service:5000 inside the container
MLFLOW_EXPERIMENT_NAME=sprintsight_experiment
LLM_AUDIT_LOG_DIR=/app/audit_logs
LLM_EVIDENCE_MODE=packed            # or legacy (30-commit JSON sample)
LLM_EVIDENCE_CONTEXT_CAP=32000      # prompt + answer tokens per call
LLM_CHARS_PER_TOKEN=3.0             # calibrated from audit_logs usage
```

Reliability and judging (all optional):

```text
OLLAMA_CONNECT_TIMEOUT_SECONDS=10   # an unreachable model server fails fast
LLM_CLIENT_MAX_RETRIES=0            # OpenAI-SDK retries for Ollama; instructor already re-asks
OPENAI_CLIENT_MAX_RETRIES=2         # same, for the hosted fixture judge
SPRINTSIGHT_JUDGE_MODEL=sprintsight-judge-phi   # one default for production and research
JUDGE_QUEUE_DB=data/judge_jobs.sqlite3          # durable judge queue; keep it on a persistent volume
JUDGE_WORKER_ENABLED=1              # 0 for one-off scripts that should not start the worker
JUDGE_JOB_MAX_ATTEMPTS=3            # then the job is marked dead, not retried forever
GRADER_MAX_WAIT_FOR_JUDGE_SECONDS=900   # grading waits this long for a running judge job
JUDGE_QUEUE_RESEARCH_FLAGS=0        # 1 to also queue gold-comparison (research) flags
```

Worst-case time for one LLM call is `(instructor max_retries + 1) x (length
re-asks + 1) x (LLM_CLIENT_MAX_RETRIES + 1) x OLLAMA_TIMEOUT_SECONDS`, so raise
retries knowing that product. The backend bounds its own wait on the engine with
`AI_ENGINE_TIMEOUT_SECONDS` (default 3600).

The judge no longer runs from FastAPI `BackgroundTasks`. After an assessment the
trace is written to a SQLite-backed queue (`evaluation/online/job_queue.py`) and a worker
thread judges it when no grading request is using the single Ollama model slot
(`evaluation/online/scheduler.py`), so a restart does not lose pending judgments and the
judge model and the grading model do not evict each other. The queue is
single-node: run one engine process per queue file.

For a clean FastAPI image rebuild:

```powershell
docker compose build --no-cache sprintsight_ai
docker compose up -d --force-recreate sprintsight_ai
```

## MLflow in SprintSight

MLflow is our single record of how a grade was produced. It runs locally in Docker, with
telemetry off (`MLFLOW_DISABLE_TELEMETRY=true`, `DO_NOT_TRACK=true`), so no student data leaves
the machine.

### Components

| Part | Where | Notes |
|---|---|---|
| Tracking server | `mlflow_service`, `http://localhost:5000` (bound to 127.0.0.1) | Built from `mlflow-server/Dockerfile`; healthcheck uses Python, because the image has no `curl` |
| Backend store | `db` (Postgres 16), database `sprintsight` | Separate from the backend's own database |
| Artifacts | named volume `mlflow_artifacts` mounted at `/mlartifacts` | Survives container recreation; do not delete the volume |
| Version | MLflow **3.16.1**, pinned | `requirements.txt`, `mlflow-server/Dockerfile` and `backend/pyproject.toml` must all match. `latest` is not used: it moved to a release whose image had no Postgres driver |

### What each assessment records

- **Experiment** `SprintSight Evaluations` (`llmops/experiments.py`), with other names for
  model comparison, the judge study and research.
- **Run** `Evaluate_Sprint_<team>_<sprint>_<model>`, tagged with `team_id`, `sprint_id`, and
  `failed_dimensions` when any dimension failed.
- **Trace**, with root span `Evaluate_Complete_Sprint`, one span per dimension
  (`Evaluate_Dimension_<name>`), `Generate_Sprint_Feedback`, and the LLM calls. Trace tags:
  `model`, `team_id`, `sprint_id`, and `prompt.Evaluate_<dimension>` (the prompt version used).
  The root span also stores `prompt_versions`.
- The API response includes `trace_id` and `experiment_name`; the backend stores `trace_id` on
  the report as the join key.

### Judge assessments (written after grading)

Written to the same trace by `evaluation/online/run_judges.py`:

| Group | Names (examples) | Source |
|---|---|---|
| Citation grounding | `citation_hallucination_rate`, `citation_grounded_rate`, `citation_severity_weighted_rate`, `citation_count`, `judge_coverage` | LLM judge |
| Code checks | `citations_dropped_by_code`, `citation_prefilter_drop_rate` | Code |
| Narrative | `justification_hard_contradictions`, `narrative_contradiction_count` | LLM judge |
| Failures | `citation_judge_failure_class`, `judge_failure_class` | Judge |
| Research only | `grade_*` (needs a gold assessment) | Code |

`citation_hallucination_rate` also carries the structured verdicts as metadata
(`sprintsight.citation_verdicts`, JSON, at most 16,000 characters; a
`sprintsight.citation_verdicts_truncated` flag says if rows were dropped). The rationale text is
cut at 2,000 characters, so the backend prefers the metadata and falls back to parsing the text
for older traces. Code: `evaluation/judges/verdict_metadata.py`.

### Human feedback written by the backend

Instructor overrides are copied to MLflow as HUMAN assessments, keyed by report UUID (never an email):

| Name | Meaning |
|---|---|
| `sprintsight.override.<dimension>` | The instructor's score (0–10), with metadata `blind=false`, `ai_score_original`, `changed`, `scale` |
| `sprintsight.instructor.<dimension>` | Blind labels (only when `INSIGHTS_MODE=blind_label`) |

HUMAN assessments are never deleted by a judge re-run.

### Prompt registry and review queue

Seven prompts are registered: `Evaluate_<dimension>` (six) and `Generate_Sprint_Feedback`. A new
version is created only when the template text changes. See "Which prompt grades?" and "Review
queues" above for the aliases and the `flagged_runs` queue.

### Reading MLflow from the backend

The backend (`backend/app/services/insightsService/mlflow_gateway.py`) is the only code outside
this service that talks to MLflow. It reads by explicit trace ID, never searches, strips prompts
and outputs from what it returns, and has a 5-second timeout. If MLflow is down, lists and scores
still load from Postgres and the trace and judge panels show a notice.

### Inspecting it

```bash
open http://localhost:5000                                  # experiments, traces, prompts
curl -s http://localhost:5000/version                       # server version
docker exec ai-engine-db-1 psql -U user -d sprintsight -c \
  "select name, source_type, count(*) from assessments group by 1,2 order by 3 desc limit 20;"
```

The instructor and admin pages built on this data (AI Insights) are described in the
[root README](../README.md#ai-insights-mlflow-in-the-ui).

### When something fails

| Symptom | Cause | What happens |
|---|---|---|
| Every dimension fails with `infra_unavailable` / `Connection error` | The container cannot reach the LLM server, usually because `SPRINTSIGHT_AI_OLLAMA_URL` is unset and the default `http://ollama:11434/v1` has no running `ollama` service | The assessment fails (`AllDimensionsFailedError`), the trace is flagged and added to `flagged_runs`, and the backend marks the report for manual review |
| A single dimension fails | Timeout, schema or length error | A placeholder score with `evaluation_failed: true`; the dimension is left out of the team score and shows "Failed dimension" in Insights |
| The judge produces no result | Judge model unreachable or context truncated | The judge status becomes `failed` or `stale` and the run shows under Needs attention |
| MLflow is down at engine start | Server stopped or unreachable | The engine logs the failed MLflow setup and prompt registration and keeps starting; tracing and prompt versioning may be unavailable until it is restarted with MLflow up |
| MLflow is down while the backend reads it | Server stopped or unreachable | The backend shows a notice instead of the trace and judge panels; lists and scores still load from Postgres |

## Running on the GPU cluster

Ollama can run on the Origami Slurm cluster and be reached through an SSH tunnel. Setup, the
per-session steps and the command reference are in [`hpc/README.md`](hpc/README.md). In `.env` set:

```text
SPRINTSIGHT_AI_OLLAMA_URL=http://host.docker.internal:11435/v1
```

The container ignores `OLLAMA_BASE_URL`: that name is for host-side research scripts, where
`localhost` is the host. The judge model `sprintsight-judge-phi` is created from `phi4:14b` and
`models/Modelfile.phi` when the Slurm job starts; if it is missing, run `bash hpc/hpc-dev.sh models`
with the tunnel open. For judge-study commands, follow
[`evaluation/offline/RUNBOOK.md`](evaluation/offline/RUNBOOK.md).
