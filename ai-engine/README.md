# SprintSight AI Engine

> Updated: September 8, 2026

SprintSight's AI engine is a local FastAPI service that evaluates synthetic
sprint artifact bundles with an Ollama model. It uses the OpenAI-compatible
Ollama API and Instructor's Pydantic response validation; no student data is
sent to a cloud LLM.

## Current Status

- The HTTP API currently evaluates fixture data from `schemas/fixtures.py`.
- Five rubric dimensions are scored: `code_quality`, `testing`,
  `documentation`, `requirements`, and `collaboration`.
- Dimension evaluations run concurrently with a limit of five active calls.
- A failed dimension is excluded from the average. The request fails only when
  all five dimensions fail.
- The evaluator returns an integer `overall_score` rounded from the average of
  the successfully scored dimensions.
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
  | POST /assess/sprint?key=...&modelname=...
  v
FastAPI (main.py, port 8001)
  |
  v
api/assessment.py
  | selects a fixture and validates query enums
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

### Create the custom Ollama models

The compose file does not pull or create models automatically. Run the
commands for the models you intend to use:

```powershell
# Llama
docker compose cp models/Modelfile.llama ollama:/tmp/Modelfile.llama
docker compose exec -T ollama ollama pull llama3.2
docker compose exec -T ollama ollama create sprintsight-llama -f /tmp/Modelfile.llama

# Qwen
docker compose cp models/Modelfile.qwen ollama:/tmp/Modelfile.qwen
docker compose exec -T ollama ollama pull qwen3:8b
docker compose exec -T ollama ollama create sprintsight-qwen -f /tmp/Modelfile.qwen

# Mistral
docker compose cp models/Modelfile.mistral ollama:/tmp/Modelfile.mistral
docker compose exec -T ollama ollama pull mistral:7b
docker compose exec -T ollama ollama create sprintsight-mistral -f /tmp/Modelfile.mistral

# Gemma
docker compose cp models/Modelfile.gemma ollama:/tmp/Modelfile.gemma
docker compose exec -T ollama ollama pull gemma4:12b
docker compose exec -T ollama ollama create sprintsight-gemma -f /tmp/Modelfile.gemma

# Verify installed models
docker compose exec ollama ollama list
```

The default model is `sprintsight-llama`. Override it with
`DEFAULT_MODEL_NAME` in `.env` or the compose environment.

## API

The AI engine accepts the backend canonical payload route:

```http
POST /assess/sprint/data?modelname=sprintsight-llama
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

### Assess a sprint fixture

```powershell
curl.exe -X POST "http://localhost:8001/assess/sprint?key=high_performing_team&modelname=sprintsight-llama"
```

The endpoint returns a `SprintAssessment` containing:

- `overall_score`: rounded score from 1 to 10
- `rubric_scores`: one optional `RubricDimensionScore` for each dimension
- `failed_dimensions`: computed list of dimensions that could not be scored
- `executive_summary`: deterministic summary based on the average
- `key_recommendations`: currently contains that summary
- `member_contributions`: currently empty because it is not generated by the
  evaluator

The request query parameters are validated using these enums:

| Parameter | Current accepted values |
|---|---|
| `key` | `high_performing_team`, `imbalanced_team`, `struggling_team` |
| `modelname` | `sprintsight-grader`, `sprintsight-llama`, `sprintsight-qwen`, `sprintsight-mistral`, `sprintsight-gemma`, plus the base model names defined in `schemas/modelname.py` |

The router's fixture map also contains experimental fixtures such as
`good_collab_low_output_team`, `lone_contributor_poor_outcome_team`, and
`imbalanced_high_output_team`. They are used by the research harness, but are
not currently selectable through the `TeamType` query enum. The enum value
`imbalanced_team` also does not currently match the fixture-map key
`imbalanced_high_output_team`; align those names in the code before relying on
that request.

## Evaluation flow

1. `api/assessment.py` validates the query parameters and selects a fixture.
2. `services/evaluator.py` starts one task per rubric dimension.
3. `services/llm_client.py` serializes the full `ArtifactBundle` and sends a
   rubric-specific prompt to Ollama.
4. Instructor validates the response as `RubricDimensionScore`, retrying up to
   three times for a dimension-level failure.
5. The evaluator collects successful dimensions, calculates their average, and
   builds `SprintAssessment`.
6. MLflow records traces and the average score. The HTTP client hooks write
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
    --models sprintsight-llama --repeats 1
```

Run a broader comparison:

```powershell
docker compose exec sprintsight_ai python -m research.validation_harness `
    --models sprintsight-llama sprintsight-mistral sprintsight-qwen sprintsight-gemma `
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
DEFAULT_MODEL_NAME=sprintsight-llama
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