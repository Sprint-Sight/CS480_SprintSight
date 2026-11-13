'''
LLM judge: do the justification, strengths, weaknesses & recomendations make sense? 
Are they consistent with the scores? Are they consistent with each other?
'''

import asyncio
from typing import Literal

import mlflow
from judges.citation_ground_custom_judge import FIXTURE_JUDGE_MODEL, judge_model_for
from mlflow.entities import (
    AssessmentSource,
    AssessmentSourceType,
    Feedback,
    SpanType,
    Trace,
)
from mlflow.genai.scorers import scorer
from prompts.dimension_criteria import DIMENSIONS
from pydantic import BaseModel, Field, model_validator
from schemas.modelname import MODEL_NUM_CTX
from services.llm_client import (
    LLM_TEMPERATURE,
    _request_extra_body,
    audit_scope,
    create_llm_client,
)

SPRINT_FEEDBACK_JUDGE_PROMPT_VERSION = "sprint_feedback_judge_v1"
SPRINT_FEEDBACK_JUDGE_PROMPT = """You check a grading report for INTERNAL consistency. You do NOT grade the students.
Scores are 1-10: 1-2 very poor, 3-5 weak, 6-8 good, 9-10 excellent. Each ITEM names a kind in brackets.
Give every item one label:
- contradicts:
    * a STRENGTH about a dimension that scored 1-3;
    * a WEAKNESS or RECOMMENDATION saying a dimension is poor or needs major work while it scored 9-10;
    * a JUSTIFICATION whose tone (praise or criticism) clearly conflicts with its own score.
- consistent: it agrees with the scores. Small polish suggestions on a dimension scored 6-8 are consistent.
- not_addressed: it cannot be compared with any dimension score (generic, or about a dimension with no score).
Ignore whether the claims are factually true. Return exactly one verdict for EVERY item id."""

class NarrativeVerdict(BaseModel):
    item_id: str
    label: Literal["consistent", "contradicts", "not_addressed"]
    reasoning: str = Field(min_length=10)

class NarrativeReport(BaseModel):
    verdicts: list[NarrativeVerdict]

def make_sprint_feedback_model(expected_ids: set[str]) -> type[NarrativeReport]:
    """Closure (instructor can't pass a validation context): a missing, unknown or duplicated id raises, so max_retries re-asks."""
    class _Checked(NarrativeReport):
        @model_validator(mode="after")
        def _every_id_once(self):
            seen = [v.item_id for v in self.verdicts]
            if len(seen) != len(set(seen)) or set(seen) != expected_ids:
                raise ValueError(f"Need exactly one verdict per id. Expected {sorted(expected_ids)}; got {sorted(seen)}")
            return self
    return _Checked

def _scored(a: dict) -> dict[str, dict]:
    return {d: s for d in DIMENSIONS if (s := (a.get("rubric_scores") or {}).get(d)) and not s.get("evaluation_failed")}

def collect_sprint_feedback_items(a: dict) -> dict[str, str]:
    items = {f"D-{d}": f"[JUSTIFICATION] {d} scored {s['score']}/10: {s['justification']}" for d, s in _scored(a).items()}
    for prefix, kind, key in (("S", "STRENGTH", "strengths"), ("W", "WEAKNESS", "weaknesses"), ("R", "RECOMMENDATION", "key_recommendations")):
        for i, text in enumerate(a.get(key) or [], 1):
            items[f"{prefix}{i}"] = f"[{kind}] {text}"
    return items

async def judge_sprint_feedback(a: dict, judge_model: str, judge_provider: str='ollama') -> dict:
    items = collect_sprint_feedback_items(a)
    scores = "\n".join(f"{d}: {s['score']}/10" for d, s in _scored(a).items())
    user = f"SCORES:\n{scores}\n\nITEMS:\n" + "\n".join(f"{k}: {v}" for k, v in items.items())
    ctx = MODEL_NUM_CTX.get(judge_model) if judge_provider == 'ollama' else None
    if judge_provider == 'ollama' and ctx is None:
        raise ValueError(f"Add '{judge_model}' to MODEL_NUM_CTX")
    if ctx is None:
        raise ValueError(f"Add '{judge_model}' to MODEL_NUM_CTX")
    with audit_scope(team_id=a.get('team_id'), sprint_id=a.get('sprint_id'), dimension="judge_sprint_feedback", model=judge_model, prompt_version=SPRINT_FEEDBACK_JUDGE_PROMPT_VERSION):
        report = await create_llm_client(provider=judge_provider).chat.completions.create(
            model=judge_model, response_model=make_sprint_feedback_model(set(items)), temperature=LLM_TEMPERATURE,
            max_retries=3, extra_body=_request_extra_body(ctx),
            messages=[{"role": "system", "content": SPRINT_FEEDBACK_JUDGE_PROMPT}, {"role": "user", "content": user}])
    contradictory_scores = [v for v in report.verdicts if v.label == "contradicts"] # contradictory scores are bad
    judged = [v for v in report.verdicts if v.label != "not_addressed"]
    just_bad = [v for v in contradictory_scores if v.item_id.startswith("D-")] # justifications are the only items that can be judged against a score
    narr_bad = [v for v in contradictory_scores if not v.item_id.startswith("D-")] # narrative items are judged against each other, not against scores
    detail = lambda vs: "; ".join(f"{v.item_id}: {v.reasoning}" for v in vs) or None
    return {"justification": (len(just_bad), detail(just_bad)), "narrative": (len(narr_bad), detail(narr_bad)),
            "rate": round(len(contradictory_scores) / len(judged), 4) if judged else None, "items": len(items)}

def _clip(s: str, n: int = 900) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."

@scorer(name="llm_judge_sprint_feedback_consistency")
def llm_judge_sprint_feedback_consistency(trace: Trace) -> list[Feedback]:
    judge_model = judge_model_for(trace)
    judge_provider = "openai" if judge_model == FIXTURE_JUDGE_MODEL else "ollama"
    source = AssessmentSource(source_type=AssessmentSourceType.LLM_JUDGE, source_id=f"{judge_provider}:/{judge_model}")
    root = next((s for s in trace.data.spans if s.parent_id is None), None)
    a = root.outputs if root is not None and isinstance(root.outputs, dict) and "rubric_scores" in root.outputs else None
    if a is None:   # older traces have no stored sprint-level feedback
        return [Feedback(name="narrative_contradiction_count", value=None,
                         rationale="trace has no stored assessment (older format)", source=source)]

    with mlflow.start_span(name="llm_judge_sprint_feedback_consistency", span_type=SpanType.LLM) as span:
        span.set_inputs({"scored_trace_id": trace.info.trace_id, "team_id": a.get("team_id"), "sprint_id": a.get("sprint_id"),
                         "judge_model": judge_model, "judge_provider": judge_provider,
                         "items": collect_sprint_feedback_items(a)})
        mlflow.update_current_trace(request_preview=_clip(f"{judge_model} consistency check on {trace.info.trace_id}"))
        try:
            r = asyncio.run(judge_sprint_feedback(a, judge_model, judge_provider))
        except Exception as e:  # noqa: BLE001
            span.set_outputs({"error_type": type(e).__name__, "error": str(e)[:1500]})
            span.set_status("ERROR")
            mlflow.update_current_trace(response_preview=_clip(f"Error {type(e).__name__}: {e}"))
            return [Feedback(name="narrative_contradiction_count", error=e, source=source)]
        span.set_outputs(r)
        mlflow.update_current_trace(response_preview=_clip(
            f"contradictions: justification={r['justification'][0]} narrative={r['narrative'][0]} of {r['items']} items"))

    return [Feedback(name="justification_hard_contradictions", value=r["justification"][0], rationale=r["justification"][1], source=source),
            Feedback(name="narrative_contradiction_count", value=r["narrative"][0], rationale=r["narrative"][1], source=source),
            Feedback(name="narrative_contradiction_rate", value=r["rate"], source=source),
            Feedback(name="narrative_item_count", value=r["items"], source=source)]