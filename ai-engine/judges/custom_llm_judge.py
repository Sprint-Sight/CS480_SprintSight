import asyncio
import os

import mlflow
from dotenv import load_dotenv
from mlflow.entities import AssessmentSource, AssessmentSourceType, Feedback, SpanType
from mlflow.genai.scorers import scorer
from schemas.benchmark_registry import FIXTURES

from judges.judge_verdict import JudgeVerdict
from llmops.prompt_registry import register_prompt_if_changed
from schemas.artifact_bundle import ArtifactBundle
from schemas.sprint_assessment import SprintAssessment
from services.llm_client import create_llm_client

load_dotenv()  # Load environment variables from .env file

DEFAULT_JUDGE_MODEL = os.getenv("SPRINTSIGHT_JUDGE_MODEL", "qwen3:8b")

JUDGE_SYSTEM_PROMPT = """
You are a strict, skeptical auditor of an AI teaching assistant's grading work.
You are NOT grading the student team. You are grading whether ANOTHER AI model
(the "candidate") graded the student team honestly and usefully.

You will be given:
  1. RAW_BUNDLE -- actual Git commits, Jira tickets, and peer evaluations.
  2. CANDIDATE_ASSESSMENT -- candidate model's full SprintAssessment.
  3. GOLD_REFERENCE -- human-authored reference assessment.

JOB 1 -- CITATION GROUNDING: Judge if RAW_BUNDLE supports each citation (grounded, partially_grounded, hallucinated).
JOB 2 -- RECOMMENDATION QUALITY: Check if recommendations are actionable and target true bottlenecks.

Return a valid JSON object matching the JudgeVerdict schema.
"""

JUDGE_USER_PROMPT_TEMPLATE = """
CANDIDATE_MODEL_UNDER_TEST: {{ candidate_model_name }}
TEAM_ID: {{ team_id }}
SPRINT_ID: {{ sprint_id }}

RAW_BUNDLE (ground truth):
{{ bundle_json }}

CANDIDATE_ASSESSMENT (what you are auditing):
{{ candidate_json }}

GOLD_REFERENCE (for identifying true bottleneck dimensions only):
{{ gold_json }}

Return your JudgeVerdict now.
"""

PROMPT_NAME, PROMPT_ALIAS = "SprintSight_Judge_Grounding_Actionability", "production"

def ensure_judge_prompt_registered() -> None:
    # Idempotent: skips re-registering when "production" already points at
    # this exact template, so repeated calls (e.g. once per judge run) don't
    # clutter the registry with identical versions.
    register_prompt_if_changed(
        name=PROMPT_NAME,
        template=JUDGE_USER_PROMPT_TEMPLATE,
        commit_message="SprintSight LLM-judge prompt (grounding + recommendation actionability)",
        alias=PROMPT_ALIAS,
        tags={"author": "SprintSight", "component": "llm-judge"},
    )

@mlflow.trace(name="LLM_Judge_Verdict", span_type=SpanType.LLM)
async def run_judge(
    bundle: ArtifactBundle,
    candidate: SprintAssessment,
    candidate_model_name: str,
    gold: SprintAssessment,
    judge_model: str,
) -> JudgeVerdict:
    client = create_llm_client()
    ensure_judge_prompt_registered()  # Guarantees the "production" alias exists before loading it below.
    loaded = mlflow.genai.load_prompt(f"prompts:/{PROMPT_NAME}@{PROMPT_ALIAS}")
    filled_user_prompt = loaded.format(
        candidate_model_name=candidate_model_name,
        team_id=bundle.team_id,
        sprint_id=bundle.sprint_id,
        bundle_json=bundle.model_dump_json(indent=2),
        candidate_json=candidate.model_dump_json(indent=2),
        gold_json=gold.model_dump_json(indent=2),
    )

    return await client.chat.completions.create(
        model=judge_model,
        response_model=JudgeVerdict,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": filled_user_prompt},
        ],
        max_retries=5,
    )

def _run_judge_sync(bundle, candidate, model_name, gold, judge_model):
    return asyncio.run(run_judge(bundle=bundle, candidate=candidate, candidate_model_name=model_name, gold=gold, judge_model=judge_model))

@scorer(name="llm_judge_grounding_and_actionability")
def llm_judge_grounding_and_actionability(inputs: dict, outputs: dict, expectations: dict) -> list[Feedback]:
    judge_source = AssessmentSource(source_type=AssessmentSourceType.LLM_JUDGE, source_id=f"ollama:/{DEFAULT_JUDGE_MODEL}")

    if not outputs:
        return [Feedback(name="citation_hallucination_rate", value=None, rationale="Candidate produced no output.", source=judge_source)]

    try:
        verdict = _run_judge_sync(
            bundle=FIXTURES[inputs["fixture_key"]],
            candidate=SprintAssessment(**outputs),
            model_name=inputs["model_name"],
            gold=SprintAssessment(**expectations["gold"]),
            judge_model=DEFAULT_JUDGE_MODEL,
        )
    except Exception as e:  # noqa: BLE001 - judge call can fail in many ways; must not crash the eval run
        return [Feedback(name="citation_hallucination_rate", error=e, rationale=f"LLM judge call failed: {e}", source=judge_source)]

    return [
        Feedback(name="citation_hallucination_rate", value=verdict.hallucination_rate, source=judge_source),
        Feedback(name="recommendation_actionability_rate", value=verdict.actionable_and_targeted_rate, source=judge_source),
        Feedback(name="judge_verdict_raw", value=verdict.model_dump_json(), source=judge_source),
    ]