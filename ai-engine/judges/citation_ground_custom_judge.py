import asyncio, os, time, mlflow
from typing import Literal

from mlflow.entities import AssessmentSource, AssessmentSourceType, Feedback, Trace, SpanType
from mlflow.genai.scorers import scorer
from pydantic import BaseModel, Field, model_validator

from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.cs203_groundtruth import CS203G6_BUNDLE, CS203JY_BUNDLE
from schemas.modelname import MODEL_NUM_CTX
from schemas.sprint_assessment import SprintAssessment
from schemas.rubrics_score import RubricsScore
from services.llm_client import audit_scope, create_llm_client, request_extra_body
from judges.trace_adapters import read_candidate

GROUNDING_PROMPT_VERSION = "grounding-v1"

GROUNDING_SYSTEM_PROMPT = """You are a strict fact-checker. You do NOT grade the students.
You check whether each CLAIM is supported by RAW_BUNDLE (real commits, Jira tickets, peer reviews).
Each claim reads "identifier | explanation". Check only facts you can verify in RAW_BUNDLE:
the identifier (commit SHA, ticket id, filename), authors, line counts, statuses, commit messages.
Ignore opinions and quality judgements (e.g. "clear message", "well structured").

Labels:
- grounded: the identifier exists in RAW_BUNDLE AND every verifiable fact in the claim is true for THAT
  record (right author, number, status or filename on the right commit/ticket).
- partially_grounded: the identifier exists but at least one verifiable fact about it is wrong or not found.
- hallucinated: the identifier does not exist in RAW_BUNDLE, or the claim contradicts it.

Return exactly one verdict for EVERY claim id given. Never skip or repeat one."""

BUNDLE_BY_TEAM = {b.team_id: b for b in (CS203G6_BUNDLE, CS203JY_BUNDLE)}
JUDGE_MODEL = os.getenv("SPRINTSIGHT_JUDGE_MODEL", "sprintsight-judge-phi")

FEEDBACK_NAMES = {"coverage": "judge_coverage", "hallucination_rate": "citation_hallucination_rate",
                  "grounded_rate": "citation_grounded_rate", "citation_count": "citation_count"}
CODE_SOURCE = AssessmentSource(source_type=AssessmentSourceType.CODE, source_id="find_ungrounded_citations")

class JudgeContextTooSmall(RuntimeError):
    """Prompt would not fit in the judge's context window; the row must be treated as invalid."""

class CitationVerdict(BaseModel):
    citation_id: str                       # "C3", the label WE gave it
    label: Literal["grounded", "partially_grounded", "hallucinated"]
    reasoning: str = Field(min_length=10)

class GroundingVerdict(BaseModel):
    citation_verdicts: list[CitationVerdict]
    judge_notes: str = Field(min_length=10)

def make_grounding_verdict_model(expected_ids: set[str]) -> type[GroundingVerdict]:
    """Closure instead of validation_context (instructor can't pass it, see services/grounding.py).
    A skipped/duplicated/unknown id raises, so instructor's max_retries re-asks with the error text."""
    class _Checked(GroundingVerdict):
        @model_validator(mode="after")
        def _every_id_exactly_once(self):
            seen = [v.citation_id for v in self.citation_verdicts]
            missing = sorted(expected_ids - set(seen))
            unknown = sorted(set(seen) - expected_ids)
            dupes = sorted({i for i in seen if seen.count(i) > 1})
            if missing or unknown or dupes:
                raise ValueError(f"Need exactly one verdict per claim id. Missing: {missing}; unknown: {unknown}; duplicated: {dupes}")
            return self
    return _Checked

def collect_citations(rubric_scores: RubricsScore) -> dict[str, dict]:
    """{"C1": {"dimension": ..., "text": "<identifier> | <reason>"}, ...}; failed dimensions are skipped."""
    labelled, n = {}, 0
    for dim in DIMENSIONS:
        #dim_score = getattr(candidate.rubric_scores, dim, None)
        dim_score = getattr(rubric_scores, dim, None)
        if dim_score is None or dim_score.evaluation_failed:
            continue
        for c in dim_score.evidence_citations:
            n += 1
            labelled[f"C{n}"] = {"dimension": dim, "text": f"{c.identifier} | {c.reason}"}
    return labelled

def summarize_verdict(citations: dict, verdict: GroundingVerdict) -> dict:
    if not citations:
        return {"coverage": None, "hallucination_rate": None, "grounded_rate": None}
    judged = {v.citation_id: v for v in verdict.citation_verdicts if v.citation_id in citations}
    n = len(judged)
    count = lambda label: sum(v.label == label for v in judged.values())
    return {
        "coverage": round(n / len(citations), 4),
        "hallucination_rate": round(count("hallucinated") / n, 4) if n else None,
        "grounded_rate": round(count("grounded") / n, 4) if n else None,
    }

async def run_grounding_judge(bundle: ArtifactBundle, citations: dict, judge_model: str) -> GroundingVerdict:
    ctx = MODEL_NUM_CTX.get(judge_model)
    if ctx is None:
        raise ValueError(f"Add '{judge_model}' to MODEL_NUM_CTX so the judge never runs on Ollama's small default context.")

    claims_text = "\n".join(f'{cid} [{c["dimension"]}]: {c["text"]}' for cid, c in citations.items())
    user_prompt = f"RAW_BUNDLE:\n{bundle.model_dump_json()}\n\nCLAIMS TO CHECK:\n{claims_text}"   # compact JSON

    est_tokens = (len(GROUNDING_SYSTEM_PROMPT) + len(user_prompt)) // 4
    if est_tokens > ctx * 0.85:
        raise JudgeContextTooSmall(f"~{est_tokens} tokens vs num_ctx {ctx} for {judge_model}")

    with audit_scope(team_id=bundle.team_id, sprint_id=bundle.sprint_id, dimension="judge_grounding",
                     model=judge_model, prompt_version=GROUNDING_PROMPT_VERSION):
        return await create_llm_client().chat.completions.create(
            model=judge_model,
            response_model=make_grounding_verdict_model(set(citations)),
            temperature=0,
            max_retries=3,
            extra_body=request_extra_body(ctx),
            messages=[
                {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

async def judge_assessment(bundle: ArtifactBundle, rubric_scores: RubricsScore, judge_model: str) -> dict:
    """Harness entry point. Raises if the judge can't give a complete verdict, so no rate is ever
    computed over a subset. Zero citations returns citation_count=0 with all rates None."""
    citations = collect_citations(rubric_scores) # Changed from Candidate SprintAssessment
    if not citations:
        return {"coverage": None, "hallucination_rate": None, "grounded_rate": None, "citation_count": 0}
    verdict = await run_grounding_judge(bundle, citations, judge_model)
    return {**summarize_verdict(citations, verdict), "citation_count": len(citations)}

@scorer(name="llm_judge_citation_grounding")
def llm_judge_citation_grounding(trace: Trace) -> list[Feedback]:
    '''
    1. Collect all citations from the candidate's rubric scores.
    2. Ask the judge to label each citation as grounded, partially grounded, or halluc
    3. Summarize the verdict into coverage, hallucination_rate, grounded_rate, and citation_count.
    4. Return Feedback objects for each of these metrics, with the judge's source.
    '''
    source = AssessmentSource(source_type=AssessmentSourceType.LLM_JUDGE, source_id=f"ollama:/{JUDGE_MODEL}")
    team, model = trace.info.tags.get("team_id"), trace.info.tags.get("model")
    print(f"\n[judge] {JUDGE_MODEL} checking {model} / {team}...", flush=True)
    start = time.perf_counter()
    with mlflow.start_span(name=f"llm_judge_citation_grounding on {model} / {team}", span_type=SpanType.LLM):
        mlflow.update_current_trace(
            request_preview=f"llm_judge_citation_grounding on {model} / {team}",
            tags={"team_id": team, "model": model, "judge_model": JUDGE_MODEL, "dimension": "judge_grounding"},
        )
        try:
            bundle = BUNDLE_BY_TEAM[team]
            rubric, dropped = read_candidate(trace, bundle) # Get the candidate's rubric scores and any citations dropped by code
            result = asyncio.run(judge_assessment(bundle, rubric, JUDGE_MODEL)) # Run the judge on the candidate's rubric scores
        except Exception as e: # Judge call can fail in many ways; must not crash the eval run
            print(f"  [judge] {model} / {team} FAILED after {time.perf_counter() - start:.0f}s: {type(e).__name__}: {e}", flush=True)
            mlflow.update_current_trace(response_preview=f"Error: {e}")
            return [Feedback(name="citation_hallucination_rate", error=e, source=source)]
        mlflow.update_current_trace(response_preview=f"Result: {result}")
        print(f"  [judge] {model} / {team} done in {time.perf_counter() - start:.0f}s: {result}", flush=True)
        return [Feedback(name=FEEDBACK_NAMES[k], value=v, source=source) for k, v in result.items()] + [
            Feedback(name="citations_dropped_by_code", value=dropped, source=CODE_SOURCE)]

