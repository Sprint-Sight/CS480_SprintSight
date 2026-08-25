# SprintSight — AI Assessment & Evaluation Service

> Automated, per-sprint grading for software engineering student teams.
> Ingests GitHub, Jira, peer evaluation, and meeting data → returns
> rubric-aligned scores across 5 dimensions using a **local AI model** (qwen, mistral, llama, gemma, etc.)
> No cloud APIs. No student data leaves your machine.

---

## Project Status (as of Aug 17)
- Currently using fake data (from `schemas.fixtures.py`) to simulate 3 types of team (High Performing, Imbalanced, Struggling)
- When main is running, it calls router in `api/assessment.py`.
- User can select team type to be graded and model to use for grading via the POST endpoint.
- The selected attributes will be sent to `services/evaluator.py`
- which then sends each rubric one by one to `services/llm_client.py`, returning `RubricsScoreDimension` one by one
- `services/evaluator.py` then calculates average score, finally returning `SprintAssessment` object  (CAN MODIFY IF TOO SIMPLE)

## Current setup process

The following workflow updates the branches, creates a feature branch, starts the
supporting services, and creates the custom Ollama models used by the AI engine.
Run the Docker commands from the `ai-engine` directory.

## Command Summary

Run these commands from the `ai-engine` directory:

```powershell

# Move into the AI engine directory
cd ai-engine

# Start PostgreSQL, Ollama, and MLflow
docker compose up -d db ollama mlflow_service

# Check that the supporting services are running
docker compose ps

# Create the Llama model
docker compose cp models/Modelfile.llama ollama:/tmp/Modelfile.llama
docker compose exec -T ollama ollama pull llama3.2
docker compose exec -T ollama ollama create sprintsight-llama -f /tmp/Modelfile.llama

# Create the Qwen model
docker compose cp models/Modelfile.qwen ollama:/tmp/Modelfile.qwen
docker compose exec -T ollama ollama pull qwen3:8b
docker compose exec -T ollama ollama create sprintsight-qwen -f /tmp/Modelfile.qwen

# Create the Mistral model
docker compose cp models/Modelfile.mistral ollama:/tmp/Modelfile.mistral
docker compose exec -T ollama ollama pull mistral:7b
docker compose exec -T ollama ollama create sprintsight-mistral -f /tmp/Modelfile.mistral

# Verify that all custom models are available
docker compose exec ollama ollama list

# Build and start the FastAPI AI service
docker compose up -d --build --force-recreate sprintsight_ai

# Follow the AI service logs
docker compose logs -f sprintsight_ai
```

The AI service is available at `http://localhost:8001`. Open the FastAPI
Swagger UI at `http://localhost:8001/docs` and MLflow at
`http://localhost:5000`.

## Verify the AI service

Run these commands from the `ai-engine` directory:

```powershell
# Check the FastAPI health endpoint
curl.exe http://localhost:8001/health

# Run a test with the Llama custom model
curl.exe -X POST "http://localhost:8001/assess/sprint?key=high_performing_team&modelname=sprintsight-llama"

# Run a test with another custom model
curl.exe -X POST "http://localhost:8001/assess/sprint?key=high_performing_team&modelname=sprintsight-qwen"

# Open the generated audit records
code .\audit_logs
```

For a completely clean FastAPI rebuild, use:

```powershell
docker compose build --no-cache sprintsight_ai
docker compose up -d --force-recreate sprintsight_ai
```

## LLM Audit Logs

Every Ollama chat-completion attempt is recorded as a separate text file in
`audit_logs/`. Each file includes the team and sprint, model, dimension, exact
request payload, raw response body, HTTP status, duration, and any exception
raised by the client. The directory is mounted into the `sprintsight_ai`
container, so the records remain on the host after the container restarts.

Open the `audit_logs` folder directly in VS Code or File Explorer. Files use
names such as `llm_20260819T141500_abc123_code_quality.txt`.

The MLflow UI at `http://localhost:5000` remains useful for experiment-level
traces and metrics. The text files are the application-owned audit records and
capture failed attempts and raw HTTP responses explicitly.

---

## What This Service Does

This microservice is the AI ENGINE of SprintSight. It sits between the
Data Preprocessing Engine (which collects raw GitHub/Jira/peer data) and the
Full-Stack Backend (which serves the instructor dashboard).

**Input →** An `ArtifactBundle`: a structured JSON payload containing one
team's complete sprint data — commits, file diffs, Jira tickets, peer
evaluation scores, and meeting logs.

**Output →** A `SprintAssessment`: a structured JSON report containing:
- An overall score (1–10)
- Individual scores for 5 rubric dimensions with written justifications
- Per-student contribution scores with supporting evidence
- An executive summary and actionable recommendations

It does this by running the AI model LOCALLY using Ollama — no OpenAI
account, no API costs, no student data sent to the cloud.

---

## Architecture Overview

```
graph LR
    LAPTOP["Get mock ArtifactBundle "]

    subgraph DOCKER["🐳 Docker Compose — runs entirely on your machine"]
        subgraph C1["📦 Container 1 — FastAPI :8001"]
            API["api/main.py\nassessment.py router"]
            EVAL["services/evaluator.py\npipeline orchestrator"]
            CLI["services/llm_client.py\nopenai client → Ollama"]
        end

        subgraph C2["📦 Container 2 — PostgreSQL :5432"]
            DB1[("prompt_registry")]
            DB2[("llm_audit_log")]
            DB3[("llm_cache")]
            DB4[("mlflow_backend")]
        end

        subgraph C3["📦 Container 3 — Ollama :11434"]
            MODEL["🤖 local model"]
        end
        
        subgraph C4["📦 Container 4 — MLflow :5000"]
            MLFLOW["🧪 MLflow Tracking Server\nActive & Wired In"]
        end
    end

    LAPTOP  -->|"POST /assess/sprint"| API
    API     --> EVAL
    EVAL   <-->|"read/write"| DB1 & DB2 & DB3
    MLFLOW <-->|"backend store"| DB4
    EVAL    --> CLI
    CLI    -->|"5 dimension calls\ninstructor + openai"| MODEL
    MODEL  -->|"RubricsDimensionScore"| CLI
    CLI     --> EVAL
    EVAL   -->|"Traces & metrics\n(@mlflow.trace & autolog)"| MLFLOW
    API    -->|"SprintAssessment"| LAPTOP
```

### Layers at a Glance

| Layer | Files | Responsibility | Status |
|:------|:------|:---------------|:-------|
| **HTTP** | `api/main.py` | Receives requests, returns responses | Working |
| **Schemas** | `schemas/artifact_bundle.py`, `schemas/assessment.py` | Define the shape of data going in and out | Working |
| **Test Data** | `schemas/fixtures.py` | Three synthetic sprint bundles for development | Working (see status of each fixture above) |
| **Business Logic** | `services/evaluator.py` | Orchestrates the full assessment pipeline | Working for well-populated data,  flaky on sparse data |
| **LLM** | `services/llm_client.py` | Connects to Ollama; enforces JSON schema via `instructor` |  Retry logic doesn't always recover malformed output |
| **Storage** | PostgreSQL tables | Cache, audit log, prompt registry | Working |
| **AI Model** | Ollama + local model | Runs locally, no cloud dependency |  Model name mismatch between docs/logs — needs confirming |
| **Experiment Tracking** | `llmops/mlflow_config.py` | Logs runs to MLflow for comparison over time | 🔄 Scaffolded, not yet wired into `evaluator.py` |

---

## Directory Structure

```
sprintsight_ai/                         ← root of this microservice
│
│   # ── Configuration ──────────────────────────────────────────
├── .env.example                        # copy to .env — all environment variables
├── docker-compose.yml                  # starts all 3 containers with one command
├── Dockerfile                          # builds the FastAPI container
├── requirements.txt                    # all Python dependencies

├── main.py

│   # ── Application Code ────────────────────────────────────────
├── api/
│   ├── __init__.py
│   └── assessment.py                   # FastAPI router: startup, lifespan, routers
│
├── schemas/
│   ├── __init__.py
│   ├── artifact_bundle.py              # ArtifactBundle: what comes IN (578 lines)
│   │                                   #   • SprintMetadata, StudentInfo
│   │                                   #   • GitHubActivity (commits, diffs, PRs)
│   │                                   #   • JiraMetrics (tickets, velocity)
│   │                                   #   • CollaborationSignals (peer evals, meetings)
│   │                                   #   • to_jinja_context()      → dict for prompts
│   │                                   #   • to_dimension_context()  → subset per dimension
│   │                                   #   • compute_hash()          → SHA-256 cache key
│   │                                   #   • count_estimated_tokens()→ ~4 chars/token
│   │                                   #   • is_over_budget()        → bool per model
│   │
│   └── fixtures.py                     # Three synthetic test bundles (447 lines)
│                                       #   • create_high_performer_sprint()
│                                       #   • create_imbalanced_sprint()
│                                       #   • create_struggling_sprint()
├── services/
│   ├── __init__.py
│   ├── evaluator.py                    # Pipeline orchestrator (483 lines) — THE BRAIN
│   │                                   #   evaluate_sprint(client, bundle) → SprintAssessment
│   │
│   └── llm_client.py                   # Ollama connection (123 lines)
│                                       #   • create_llm_client() → AsyncInstructor
│                                       #     openai client with base_url=OLLAMA_BASE_URL
│                                       #     instructor wraps it to enforce Pydantic schema
│                                       #   • also runnable directly: `python -m services.llm_client`
│                                       #     — useful for quick manual testing against one fixture
├── llmops/
│   ├── mlflow_config.py                #     MLflow tracking config, logs metrics and traces
```

---

## File-by-File Guide

### How the files depend on each other

```
tests/test_endpoint.py
    │ imports
    ▼
schemas/fixtures.py  ──────────────────────────────────────────────────┐
    │ creates ArtifactBundle (defined in)                               │
    ▼                                                                   │
schemas/artifact_bundle.py                                             │
    │ sent via HTTP POST to                                             │
    ▼                                                                   │
api/main.py  →  POST /assess/sprint  →  evaluate_sprint()             │
                                               │                        │
                                               │ orchestrated by        │
                                               ▼                        │
                               services/evaluator.py                   │
                                   │         │                          │
                        calls      │         │  validates responses     │
                               ▼         ▼                          │
                  services/llm_client.py    schemas/assessment.py  ◄──┘
                               │            (Pydantic enforces shape)
                               │
                               ▼
                          Ollama :11434
                          local model
                          (running locally — see Known Issues re: which model)
```

### Quick reference: which file to open when something goes wrong

| Problem | Look in |
|:--------|:--------|
| HTTP request fails | `api/main.py` — check routers and startup |
| Wrong input data shape | `schemas/artifact_bundle.py` |
| AI returns wrong format / malformed JSON | `schemas/assessment.py` (the Pydantic schema) and `services/llm_client.py` (retry/parse logic) — **this is our current #1 bug, see Known Issues** |
| Scores are inaccurate | `services/evaluator.py` — the prompts sent to Ollama |
| Ollama not responding | `services/llm_client.py` — check health, URL, model name |
| Test fixture data wrong | `schemas/fixtures.py` — edit the synthetic data |
| Docker won't start | `docker-compose.yml` — check ports and volumes |
| MLflow won't start / not logging anything | `llmops/mlflow_config.py` — remember it isn't called from the pipeline yet |

## The Assessment Pipeline: Step by Step

When `POST /assess/sprint` receives an `ArtifactBundle`, this is the exact
sequence of events inside `services/evaluator.py`:

```
1. HASH
   SHA-256(bundle content) → unique cache key
   f"<64-char-hex>:v1.0.0"

2. CACHE CHECK
   Query PostgreSQL llm_cache table
   ├── Hit  → return stored SprintAssessment immediately (milliseconds)
   └── Miss → continue to step 3

3. PROMPT FETCH
   Query PostgreSQL prompt_registry table
   Fetch 5 active Jinja2 templates (one per dimension)

4. RENDER × 5
   For each dimension:
     renderer fills template with bundle.to_dimension_context(dimension)
     token_counter checks the rendered prompt fits in model context window
     If over budget → truncate diff_excerpts and re-render

5. CONCURRENT LLM CALLS  ⚠️ see Known Issues
   asyncio.gather launches all 5 evaluation tasks simultaneously
   Each task:
     openai client (pointed at Ollama) → POST /v1/chat/completions
     instructor enforces response matches RubricDimensionScore schema
     tenacity retries up to 5× on failure (schema mismatch or timeout)
   This is where malformed-JSON failures currently show up on sparse
   input data — see Known Issues for actual logs.

6. AGGREGATE
   5 × RubricDimensionScore collected
   Member contributions evaluated (6th LLM call)
   Executive summary generated (7th LLM call)
   overall_score = mean of 5 dimension scores
   SprintAssessment assembled

7. PERSIST
   Write SprintAssessment to llm_cache (next identical request = instant)
   Write raw I/O + latency + token counts to llm_audit_log (background task)

8. RETURN
   200 OK {SprintAssessment JSON}
```

## Database Tables

PostgreSQL stores three tables, auto-created when the service starts.

### `prompt_registry`

Stores the Jinja2 prompt templates used to ask the AI each question.

| Column | Type | Description |
|:-------|:-----|:------------|
| `id` | UUID | Primary key |
| `dimension` | VARCHAR | `code_quality`, `testing`, `documentation`, `requirements`, `collaboration` |
| `version` | VARCHAR | e.g. `v1.0.0` |
| `system_template` | TEXT | Instructions and rubric criteria for the AI |
| `user_template` | TEXT | The actual sprint data injected per evaluation |
| `is_active` | BOOLEAN | Only one version is active per dimension at a time |
| `created_at` | TIMESTAMPTZ | When this version was created |

## CITATION
```
@software{liu2024instructor,
  author = {Jason Liu and Contributors},
  title = {Instructor: A library for structured outputs from large language models},
  url = {https://github.com/instructor-ai/instructor},
  year = {2024},
  month = {3}
}
```