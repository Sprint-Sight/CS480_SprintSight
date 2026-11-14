import asyncio
import os
import time
from typing import Literal

import mlflow
from benchmarks.cs203 import CS203G6_BUNDLE, CS203JY_BUNDLE
from judges.trace_adapters import read_candidate
from mlflow.entities import (
    AssessmentSource,
    AssessmentSourceType,
    Feedback,
    SpanType,
    Trace,
)
from mlflow.genai.scorers import scorer
from pydantic import BaseModel, Field, create_model, model_validator

from prompts.dimension_criteria import DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.bundle_registry import get_bundle
from schemas.modelname import MODEL_NUM_CTX
from schemas.rubrics_score import RubricsScore
from services.llm_client import (
    LLM_TEMPERATURE,
    _request_extra_body,
    audit_scope,
    create_llm_client,
)

# V2 adds severity labels to partially_grounded and hallucinated, and clarifies that the judge should not grade the student, only check facts.
GROUNDING_PROMPT_VERSION = "grounding-v2"

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

Severity (required; it must fit the label):
- none: only for grounded claims.
- minor_detail: the identifier is real and the error is small (wrong line count, off-by-one line range, reworded message).
- major_misattribution: the identifier is real but the claim uses it wrongly (wrong author, wrong ticket status, wrong file,
  a feature the commit does not contain), or the claim contradicts the record.
partially_grounded takes minor_detail or major_misattribution; hallucinated always takes major_misattribution.
Citations to things that do not exist were already removed by code; you will not see them.

Return exactly one verdict for EVERY claim id given. Never skip or repeat one."""

BUNDLE_BY_TEAM = {b.team_id: b for b in (CS203G6_BUNDLE, CS203JY_BUNDLE)}
JUDGE_MODEL = os.getenv("SPRINTSIGHT_JUDGE_MODEL", 'sprintsight-judge-phi')
FIXTURE_JUDGE_MODEL = "gpt-4o-mini"  # Ollama judge for fixtures, OpenAI judge for real runs

FEEDBACK_NAMES = {"coverage": "judge_coverage", "hallucination_rate": "citation_hallucination_rate",
                  "grounded_rate": "citation_grounded_rate", "citation_count": "citation_count"}
CODE_SOURCE = AssessmentSource(source_type=AssessmentSourceType.CODE, source_id="find_ungrounded_citations")

Severity = Literal["none", "minor_detail", "major_misattribution"]
SEVERITY_WEIGHT = {"none": 0.0, "minor_detail": 0.25, "major_misattribution": 0.6}
CODE_DROP_WEIGHT = 1.0           # a citation code had to remove is a fabrication
_ALLOWED_SEVERITY = {"grounded": {"none"}, "partially_grounded": {"minor_detail", "major_misattribution"},
                     "hallucinated": {"major_misattribution"}}

def judge_model_for(trace):
    return FIXTURE_JUDGE_MODEL if trace.info.tags.get("fixture") == "true" else JUDGE_MODEL

class JudgeContextTooSmall(RuntimeError):
    """Prompt would not fit in the judge's context window; the row must be treated as invalid."""

class CitationVerdict(BaseModel):
    citation_id: str                       # "C3", the label WE gave it
    reasoning: str = Field(min_length=10)  # before the label on purpose: the model explains first, then decides
    label: Literal["grounded", "partially_grounded", "hallucinated"]
    severity: Severity

    @model_validator(mode="after")
    def _severity_fits_label(self):
        if self.severity not in _ALLOWED_SEVERITY[self.label]:
            raise ValueError(f"{self.citation_id}: label '{self.label}' needs severity in {sorted(_ALLOWED_SEVERITY[self.label])}, got '{self.severity}'")
        return self

class GroundingVerdict(BaseModel):
    citation_verdicts: list[CitationVerdict]
    judge_notes: str = Field(min_length=10)

def make_grounding_verdict_model(expected_ids: set[str]) -> type[GroundingVerdict]:
    """Closure instead of validation_context (instructor can't pass it, see services/grounding.py).
    A skipped/duplicated/unknown id raises, so instructor's max_retries re-asks with the error text."""
    
    id_type = Literal[tuple(sorted(expected_ids))]  # type: ignore[valid-type]  # runtime-built enum of the allowed ids

    verdict_cls = create_model(
        "_Verdict", __base__=CitationVerdict,
        citation_id=(id_type, Field(description="Exactly the claim id (C1, C2, ...). Never a commit SHA or ticket key.")),
    )
    base = create_model("_CheckedBase", __base__=GroundingVerdict, citation_verdicts=(list[verdict_cls], ...))

    class _Checked(base):
        @model_validator(mode="after")
        def _every_id_exactly_once(self):
            seen = [v.citation_id for v in self.citation_verdicts]
            missing = sorted(expected_ids - set(seen))
            dupes = sorted({i for i in seen if seen.count(i) > 1})
            if missing or dupes:
                raise ValueError(f"Need exactly one verdict per claim id. Missing: {missing}; duplicated: {dupes}")
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
        return {"coverage": None, "hallucination_rate": None, "grounded_rate": None, 'severity_weighted_rate': None}
    judged = {v.citation_id: v for v in verdict.citation_verdicts if v.citation_id in citations}
    n = len(judged)
    count = lambda label: sum(v.label == label for v in judged.values())
    return {
        "coverage": round(n / len(citations), 4),
        "hallucination_rate": round(count("hallucinated") / n, 4) if n else None,
        "grounded_rate": round(count("grounded") / n, 4) if n else None,
        "severity_weighted_rate": round(sum(SEVERITY_WEIGHT[v.severity] for v in judged.values()) / n, 4) if n else None,
    }

# Main entry point for the grounding judge, get the judge's verdict and the per-citation rows for logging.
async def run_grounding_judge(bundle: ArtifactBundle, citations: dict, judge_model: str, judge_provider: str = 'ollama') -> GroundingVerdict:
    if judge_provider == 'ollama':
        ctx = MODEL_NUM_CTX.get(judge_model)
        if ctx is None:
            raise ValueError(f"Add '{judge_model}' to MODEL_NUM_CTX so the judge never runs on Ollama's small default context.")
        extra_body = _request_extra_body(ctx)
        ctx_for_estimate = ctx
    else:
        extra_body = {}
        ctx_for_estimate = 128_000 # gpt-4o-mini's context window

    claims_text = "\n".join(f'{cid} [{c["dimension"]}]: {c["text"]}' for cid, c in citations.items())
    user_prompt = f"RAW_BUNDLE:\n{bundle.model_dump_json()}\n\nCLAIMS TO CHECK:\n{claims_text}"   # compact JSON

    est_tokens = (len(GROUNDING_SYSTEM_PROMPT) + len(user_prompt)) // 4
    if est_tokens > ctx_for_estimate * 0.85:
        raise JudgeContextTooSmall(f"~{est_tokens} tokens vs num_ctx {ctx_for_estimate} for {judge_model}")

    with audit_scope(team_id=bundle.team_id, sprint_id=bundle.sprint_id, dimension="judge_grounding",
                     model=judge_model, prompt_version=GROUNDING_PROMPT_VERSION):
        return await create_llm_client(provider=judge_provider).chat.completions.create(
            model=judge_model,
            response_model=make_grounding_verdict_model(set(citations)),
            temperature=LLM_TEMPERATURE,
            max_retries=3,
            extra_body=extra_body,
            messages=[
                {"role": "system", "content": GROUNDING_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

async def judge_assessment(bundle: ArtifactBundle, rubric_scores: RubricsScore, judge_model: str, judge_provider: str = 'ollama') -> dict:
    return (await judge_assessment_detailed(bundle, rubric_scores, judge_model, judge_provider))[0]

# Detailed assessment adds per-dimension hallucination rates and a row per judged citation, 
async def judge_assessment_detailed(bundle: ArtifactBundle, rubric_scores: RubricsScore, judge_model: str, judge_provider: str = 'ollama') -> tuple[dict, list[dict]]:
    """Harness entry point. Raises if the judge can't give a complete verdict, so no rate is ever
    computed over a subset. Returns (metrics, rows): one row per judged citation, for rationales and later logging.
    Zero citations returns citation_count=0 with all rates None and no rows."""
    citations = collect_citations(rubric_scores) # Changed from Candidate SprintAssessment
    if not citations:
        return {"coverage": None, "hallucination_rate": None, "grounded_rate": None,
                "severity_weighted_rate": None, "citation_count": 0}, []
    verdict = await run_grounding_judge(bundle, citations, judge_model, judge_provider)
    by_dim: dict[str, list[str]] = {}
    for v in verdict.citation_verdicts: # Judge emit a rate per dimension
        by_dim.setdefault(citations[v.citation_id]["dimension"], []).append(v.label)
    per_dim = {f"hallucination_rate_{d}": round(l.count("hallucinated") / len(l), 4) for d, l in by_dim.items()}
    rows = [{"citation_id": v.citation_id, "dimension": citations[v.citation_id]["dimension"],
             "claim": citations[v.citation_id]["text"], "label": v.label, "severity": v.severity,
             "reasoning": v.reasoning} for v in verdict.citation_verdicts]
    return {**summarize_verdict(citations, verdict), **per_dim, "citation_count": len(citations)}, rows

# Treat judge's verdict as set of metrics, 
# so the caller can log them as Feedback objects with the judge's source. 
# Each row is a judged citation, for later logging.
@scorer(name="llm_judge_citation_grounding")
def llm_judge_citation_grounding(trace: Trace) -> list[Feedback]:
    '''
    1. Determine if the trace is a fixture (uses OpenAI judge) or not (uses Ollama judge).
    2. Get the team_id and sprint_id from the trace tags.
    3. Get the corresponding ArtifactBundle for the team_id and sprint_id.
    4. Read the candidate's rubric scores and any citations dropped by code.
    5. Run the judge on the candidate's rubric scores.
    6. If the judge fails, log the error and return a Feedback object with the error.
    7. If the judge succeeds, compute the number of judged citations and the weighted sum of their severities.
    8. Return a list of Feedback objects with the judge's verdict and any citations dropped by code.
    '''

    judge_model = judge_model_for(trace)
    judge_provider = "openai" if judge_model == FIXTURE_JUDGE_MODEL else "ollama"

    source = AssessmentSource(source_type=AssessmentSourceType.LLM_JUDGE, source_id=f"{judge_provider}:/{judge_model}")
    team, model = trace.info.tags.get("team_id"), trace.info.tags.get("model")
    print(f"\n[judge] {judge_model} (using {judge_provider}) checking {model} / {team}...", flush=True)

    start = time.perf_counter()
    with mlflow.start_span(name=f"llm_judge_citation_grounding on {model} / {team}", span_type=SpanType.LLM) as span:
        
        span.set_inputs({"scored_trace_id": trace.info.trace_id, "team_id": team,
                         "sprint_id": trace.info.tags.get("sprint_id"), "candidate_model": model,
                         "judge_model": judge_model, "judge_provider": judge_provider})
        
        mlflow.update_current_trace(
            request_preview=f"llm_judge_citation_grounding on {model} / {team}",
            tags={"team_id": team, "model": model, "judge_model": judge_model, "judge_provider": judge_provider, "dimension": "judge_grounding"},
        )

        try:
            bundle = _bundle_of(trace, team)
            rubric, dropped = read_candidate(trace, bundle) # Get the candidate's rubric scores and any citations dropped by code
            result, rows = asyncio.run(judge_assessment_detailed(bundle, rubric, judge_model, judge_provider)) # Run the judge on the candidate's rubric scores
        
        except Exception as e:  # noqa: BLE001 - judge call can fail in many ways; must not crash the eval run
            print(f"  [judge] {model} / {team} FAILED after {time.perf_counter() - start:.0f}s: {type(e).__name__}: {e}", flush=True)
            span.set_outputs({"error_type": type(e).__name__, "error": str(e)[:1500]})
            span.set_status("ERROR")
            mlflow.update_current_trace(response_preview=_clip(f"Error {type(e).__name__}: {e}"))
            mlflow.update_current_trace(response_preview=f"Error: {e}"[:900])
            return [Feedback(name="citation_hallucination_rate", error=e, source=source)]
        
        span.set_outputs({"metrics": result, "citations_dropped_by_code": dropped, "verdicts": rows})
        mlflow.update_current_trace(response_preview=_clip(
            f"halluc={result['hallucination_rate']} grounded={result['grounded_rate']} "
            f"cites={result['citation_count']} dropped={dropped}"))
        print(f"  [judge] {model} / {team} done in {time.perf_counter() - start:.0f}s: {result}", flush=True)
        n, wsum = result["citation_count"], sum(SEVERITY_WEIGHT[r["severity"]] for r in rows)
        headline = round((wsum + CODE_DROP_WEIGHT * dropped) / (n + dropped), 4) if n + dropped else None
        why = "\n".join(f'{r["citation_id"]} [{r["dimension"]}] {r["label"]}/{r["severity"]}: {r["reasoning"]}'
                        for r in rows if r["label"] != "grounded")[:2000] or "every judged citation was grounded"
        
        return [Feedback(name=_feedback_name(k), value=v, source=source,
                         rationale=why if k in ("hallucination_rate", "severity_weighted_rate") else None)
                for k, v in result.items()] + [
            Feedback(name="citations_dropped_by_code", value=dropped, source=CODE_SOURCE,
                     rationale="citations removed by code before the judge ran; each is a fabrication"),
            Feedback(name="citation_prefilter_drop_rate", value=round(dropped / (dropped + n), 4) if dropped + n else None, source=CODE_SOURCE),
            Feedback(name="citation_severity_weighted_rate_incl_dropped", value=headline, source=source,
                     rationale=f"{n} judged citations (weight sum {wsum}) plus {dropped} code-removed fabrications at weight {CODE_DROP_WEIGHT}")]

def _fixture_bundle(team: str | None):
    from research.cs203_groundtruth import CS203G6_BUNDLE, CS203JY_BUNDLE
    from research.fixtures import FIXTURES_TEAMS
    return {b.team_id: b for b in (CS203G6_BUNDLE, CS203JY_BUNDLE, *FIXTURES_TEAMS)}.get(team)

def _bundle_of(trace: Trace, team: str | None) -> ArtifactBundle:
    root = next((s for s in trace.data.spans if s.parent_id is None), None)
    inputs = (root.inputs or {}) if root is not None and isinstance(root.inputs, dict) else {}
    if inputs.get("bundle"):
        return ArtifactBundle.model_validate(inputs["bundle"])
    bundle = get_bundle(team, inputs.get("sprint_id")) or _fixture_bundle(team)
    if bundle is None:
        raise KeyError(f"no bundle for team={team!r} sprint={inputs.get('sprint_id')!r}")
    return bundle

def _clip(s: str, n: int = 900) -> str: # trace_info preview conlumns are varchar(1000)
    return s if len(s) <= n else s[: n - 3] + "..."

def _feedback_name(key: str) -> str: # known keys keep their names
    return FEEDBACK_NAMES.get(key, f'citation_{key}')