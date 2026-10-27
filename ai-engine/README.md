# SprintSight AI Engine

> Updated: September 8, 2026

SprintSight's AI engine is a local FastAPI service that evaluates ingested
sprint artifact bundles with an Ollama model. It uses the OpenAI-compatible
Ollama API and Instructor's Pydantic response validation; no student data is
sent to a cloud LLM.

## Current Status

- The HTTP API evaluates sprint data ingested by the backend from Git, Jira,
  and uploaded documents.
- Five rubric dimensions are scored: `code_quality`, `testing`,
  `documentation`, `requirements`, and `collaboration`.
- Dimension evaluations run concurrently with a limit of five active calls.
- A dimension that fails after retries is filled with a conservative
  placeholder score (`evaluation_failed: true`) instead of being excluded, so
  all 5 dimensions are always present in the average and in the response.
- The evaluator returns a float `overall_score` (average of the 5 dimensions,
  rounded to 2 decimal places) — not rounded to an integer, since the backend
  multiplies it by 10 for its /100 team score and integer rounding here would
  collapse that /100 score down to multiples of 10.
- `member_contributions` is currently returned as its default empty list; the
  evaluator does not generate individual contribution scores yet.
- Each Ollama request and raw response is written to a text audit record,
  including failed requests.
- MLflow tracing, OpenAI autologging, and benchmark runs are supported. The
  MLflow prompt registry is initialized at startup, but the evaluator sends
  the rubric prompts defined in `schemas/rubrics_score.py` directly.

## Architecture

```text
Client
  |
  | POST /assess/sprint/data?modelname=...
  v
FastAPI (main.py, port 8001)
  |
  v
api/assessment.py
  | validates and converts the ingested payload
  v
services/evaluator.py
  | concurrently evaluates five rubric dimensions
  v
services/llm_client.py
  | Instructor + OpenAI client
  v
Ollama (port 11434)

MLflow (port 5000) receives traces, metrics, and prompt-registry data.
PostgreSQL (port 5432) is used as MLflow's backend store.
```

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
- `rubric_scores`: one `RubricDimensionScore` for each of the 5 dimensions —
  always present; if a dimension's evaluation failed after retries, it is
  filled with a conservative placeholder score and `evaluation_failed: true`
  instead of being omitted
- `failed_dimensions`: computed list of dimensions that could not be scored
  (i.e. flagged with `evaluation_failed: true`)
- `executive_summary`: deterministic summary based on the average
- `key_recommendations`: currently contains that summary
- `member_contributions`: currently empty because it is not generated by the
  evaluator

## Evaluation flow

1. The backend ingests Git, Jira, and document data and sends the canonical
  payload to `api/assessment.py`.
2. `api/assessment.py` validates the payload and builds an `ArtifactBundle`.
3. `services/evaluator.py` starts one task per rubric dimension.
4. `services/llm_client.py` serializes the full `ArtifactBundle` and sends
   rubric-specific prompt to Ollama.
5. Instructor validates the response as `RubricDimensionScore`, retrying up to
   three times for a dimension-level failure.
6. The evaluator collects successful dimensions, calculates their average, and
   builds `SprintAssessment`.
7. MLflow records traces and the average score. The HTTP client hooks write
   request/response audit files under `audit_logs/`.

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
docker compose exec sprintsight_ai python -m research.validation_harness `
    --models sprintsight-qwen --repeats 1
```

Run a broader comparison:

```powershell
docker compose exec sprintsight_ai python -m research.validation_harness `
    --models sprintsight-qwen sprintsight-mistral sprintsight-gemma `
    --repeats 5
```

Each fixture/model/repeat evaluates five dimensions, so larger runs can take
considerable time on local hardware.

## Useful files

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app, lifespan setup, and `/health` |
| `api/assessment.py` | Assessment route, query enums, and fixture selection |
| `services/evaluator.py` | Dimension orchestration and score aggregation |
| `services/llm_client.py` | Ollama client, structured output, retries, and health checks |
| `services/audit_logger.py` | Human-readable LLM request/response records |
| `schemas/fixtures.py` | Synthetic artifact bundles |
| `schemas/rubrics_score.py` | Rubric dimensions and grading prompts |
| `research/validation_harness.py` | Multi-model validation experiments |
| `docker-compose.yaml` | Ollama, FastAPI, MLflow, and PostgreSQL services |

## Configuration

The main environment variables are:

```text
OLLAMA_BASE_URL=http://ollama:11434/v1
OLLAMA_TIMEOUT_SECONDS=300
DEFAULT_MODEL_NAME=sprintsight-qwen
MLFLOW_TRACKING_URI=http://mlflow_service:5000
MLFLOW_EXPERIMENT_NAME=sprintsight_experiment
LLM_AUDIT_LOG_DIR=/app/audit_logs
```

For a clean FastAPI image rebuild:

```powershell
docker compose build --no-cache sprintsight_ai
docker compose up -d --force-recreate sprintsight_ai
```

## Why MLFLOW?
1. You can run it in your own laptop
2. Compatible with any open telemetry
3. Continuous monitoring of funds actually deployment.
4. All-in-one unifited platform to perform `tracing`, `tracking`, `evaluation`.

# Prompt Registry
- Track params & prompts (prompt version)   
- Test different versions of the prompt (A/B testing)
- Register prompt by dimensions. Compare within each dimension various prompts and their results

# Tracing
- See duration of execution
- Helps you figure out where potential bottlenecks lies in
- Ability to look at your your LLM is doing at every step while executing its task (ex. talk to DB, executing web search, local tools, etc.)

# Evaluation
- Can provide human feedback, LLM can take feedback and improve on it for next iterations
- Comprehensive set of agent dashboards and LLM judge metrics

# Gateway (Unlikely for our project?)
- Control & audit who is actually doing what LLMs were called and provide agents access

## The Evaluation Challenge (2:14 - 3:08):

Beyond Math: Unlike traditional machine learning models (e.g., linear regression), where outputs can be easily validated with quantitative metrics, generative AI requires a qualitative understanding. It is difficult to mathematically define if a model's long-form response is accurate, concise, or contextually appropriate.
Complexity of Data: Modern agentic workflows involve intricate metadata, such as tool calls and retrieval steps, which are hard to assess using simple string-matching metrics like ROUGE or F1 score.
How LLM-as-a-Judge Rescues the Process (3:08 - 6:02):

Interpreting Traces: An LLM-as-a-judge uses a trace—the fundamental unit of logging for an AI's inference call—to inspect inputs, outputs, and specific events like tool calls (3:36).
Defining Rubrics: By providing the judge LLM with a system prompt, you can define your own evaluation criteria or scoring rubrics (e.g., a 1-to-5 scale), allowing the judge to provide nuanced, qualitative feedback on whether the agent performed as expected (4:02).
Ground Truth Integration: You can pass in an evaluation set with expected outcomes (the "gold standard"), allowing the judge to compare the agent's behavior against your desired criteria and determine if the model followed the correct course of action (4:37).