"""The grounding judge: verdict weights, per-dimension metrics, truncation guard, config."""

import asyncio
from types import SimpleNamespace

import pytest

from judges import citation_ground_custom_judge as judge
from judges.citation_ground_custom_judge import (
    CODE_DROP_WEIGHT,
    VERDICT_WEIGHT,
    CitationVerdict,
    GroundingVerdict,
    JudgeContextTruncated,
    _feedback_name,
    judge_assessment_detailed,
    make_grounding_verdict_model,
    summarize_verdict,
    verdict_weight,
)
from judges.judge_config import DEFAULT_JUDGE_MODEL, configured_judge_model
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import (
    ResolvedEvidenceCitation,
    RubricDimensionScore,
)
from schemas.rubrics_score import RubricsScore
from services import llm_client

GROUNDED = ("grounded", "none")
MINOR = ("partially_grounded", "minor_detail")
WRONG_ATTRIBUTION = ("partially_grounded", "major_misattribution")
CONTRADICTED = ("hallucinated", "major_misattribution")


def _verdict(cid: str, kind: tuple[str, str]) -> CitationVerdict:
    return CitationVerdict(citation_id=cid, reasoning="Because the record says so.", label=kind[0], severity=kind[1])


# ------------------------------------------------------------------------- weights


def test_a_contradicted_citation_weighs_more_than_a_wrong_attribution() -> None:
    # Both used to be 0.6, so the severity-weighted rate could not tell them apart.
    assert verdict_weight(*CONTRADICTED) > verdict_weight(*WRONG_ATTRIBUTION)


def test_weights_are_strictly_ordered_up_to_a_code_removed_fabrication() -> None:
    ordered = [verdict_weight(*kind) for kind in (GROUNDED, MINOR, WRONG_ATTRIBUTION, CONTRADICTED)]
    assert ordered == sorted(set(ordered))  # strictly increasing, no ties
    assert ordered[0] == 0.0
    assert ordered[-1] < CODE_DROP_WEIGHT  # an identifier that does not exist is the worst case


def test_every_label_severity_pair_the_judge_may_emit_has_a_weight() -> None:
    allowed = {
        ("grounded", "none"),
        ("partially_grounded", "minor_detail"),
        ("partially_grounded", "major_misattribution"),
        ("hallucinated", "major_misattribution"),
    }
    assert set(VERDICT_WEIGHT) == allowed


def test_summarize_verdict_uses_the_label_aware_weights() -> None:
    citations = {f"C{i}": {"dimension": "testing", "text": "x | y"} for i in range(1, 5)}
    verdict = GroundingVerdict(
        citation_verdicts=[_verdict("C1", GROUNDED), _verdict("C2", MINOR),
                           _verdict("C3", WRONG_ATTRIBUTION), _verdict("C4", CONTRADICTED)],
        judge_notes="Mixed bag of citations.",
    )

    summary = summarize_verdict(citations, verdict)

    assert summary["severity_weighted_rate"] == round((0 + 0.2 + 0.5 + 0.8) / 4, 4)
    assert summary["hallucination_rate"] == 0.25
    assert summary["grounded_rate"] == 0.25


def test_the_verdict_validator_still_rejects_an_impossible_label_severity_pair() -> None:
    with pytest.raises(ValueError, match="needs severity"):
        CitationVerdict(citation_id="C1", reasoning="Because the record says so.",
                        label="grounded", severity="major_misattribution")


def test_the_judge_must_return_exactly_one_verdict_per_claim() -> None:
    model = make_grounding_verdict_model({"C1", "C2"})
    with pytest.raises(ValueError, match="Missing"):
        model(citation_verdicts=[_verdict("C1", GROUNDED)], judge_notes="Skipped one claim.")


# ------------------------------------------------------- per-dimension metrics


def _rubric(**dimension_citations: int) -> RubricsScore:
    scores = {}
    for name, n in dimension_citations.items():
        citations = [ResolvedEvidenceCitation(identifier=f"id-{i}", reason="Because of this evidence.") for i in range(n)]
        scores[name] = RubricDimensionScore(
            dimension=name, score=7, justification="A justification.", evidence_citations=citations
        )
    return RubricsScore(**scores)


def test_per_dimension_counts_and_rates_are_reported(monkeypatch) -> None:
    rubric = _rubric(testing=2, cicd=1)  # C1, C2 = testing (in DIMENSIONS order they come out C?, see ids)
    citations = judge.collect_citations(rubric)
    ids_by_dim = {}
    for cid, c in citations.items():
        ids_by_dim.setdefault(c["dimension"], []).append(cid)
    kinds = {ids_by_dim["testing"][0]: GROUNDED, ids_by_dim["testing"][1]: CONTRADICTED, ids_by_dim["cicd"][0]: MINOR}

    async def fake_judge(bundle, cits, model, provider="ollama"):
        return GroundingVerdict(
            citation_verdicts=[_verdict(cid, kind) for cid, kind in kinds.items()], judge_notes="Done judging."
        )

    monkeypatch.setattr(judge, "run_grounding_judge", fake_judge)

    metrics, rows = asyncio.run(judge_assessment_detailed(SimpleNamespace(), rubric, "m"))

    assert metrics["citation_count"] == 3
    assert metrics["citation_count_testing"] == 2 and metrics["citation_count_cicd"] == 1
    assert metrics["hallucination_rate_testing"] == 0.5 and metrics["hallucination_rate_cicd"] == 0.0
    assert metrics["severity_weighted_rate_testing"] == round((0.0 + 0.8) / 2, 4)
    assert metrics["severity_weighted_rate_cicd"] == 0.2
    assert "citation_count_documentation" not in metrics  # a dimension with no citations is absent, not zero
    assert len(rows) == 3


def test_feedback_names_are_not_double_prefixed() -> None:
    assert _feedback_name("hallucination_rate") == "citation_hallucination_rate"
    assert _feedback_name("severity_weighted_rate") == "citation_severity_weighted_rate"
    assert _feedback_name("citation_count") == "citation_count"
    assert _feedback_name("citation_count_testing") == "citation_count_testing"
    assert _feedback_name("severity_weighted_rate_testing") == "citation_severity_weighted_rate_testing"
    assert _feedback_name("hallucination_rate_testing") == "citation_hallucination_rate_testing"


# --------------------------------------------------------------- truncation guard


def _stub_llm(monkeypatch, *, prompt_tokens: int, num_ctx_seen: list):
    """Make the judge's LLM call 'complete' with a server-reported prompt size, going through
    the real audit context and truncation check."""
    verdict = GroundingVerdict(citation_verdicts=[_verdict("C1", GROUNDED)], judge_notes="All claims fine.")

    class Completions:
        async def create(self, **kwargs):
            context = llm_client._audit_context.get()
            num_ctx_seen.append(context["num_ctx"])
            body = f'{{"usage": {{"prompt_tokens": {prompt_tokens}}}, "choices": [{{"finish_reason": "stop"}}]}}'
            if llm_client._prompt_truncated(body, context):
                context["prompt_truncated"] = True
            return verdict

    monkeypatch.setattr(
        judge, "create_llm_client", lambda provider="ollama": SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    )
    monkeypatch.setattr(judge, "MODEL_NUM_CTX", {"judge-x": 10_000})


def test_a_prompt_cut_by_the_server_is_discarded_not_judged(monkeypatch) -> None:
    seen: list = []
    _stub_llm(monkeypatch, prompt_tokens=9_900, num_ctx_seen=seen)  # >= 98% of num_ctx: Ollama cut it

    bundle = ArtifactBundle(team_id="t", sprint_id="s")
    with pytest.raises(JudgeContextTruncated):
        asyncio.run(judge.run_grounding_judge(bundle, {"C1": {"dimension": "testing", "text": "a | b"}}, "judge-x"))

    assert seen == [10_000]  # num_ctx reached the audit context, which is what lets the check fire


def test_a_healthy_prompt_is_judged_normally(monkeypatch) -> None:
    _stub_llm(monkeypatch, prompt_tokens=2_000, num_ctx_seen=[])

    bundle = ArtifactBundle(team_id="t", sprint_id="s")
    verdict = asyncio.run(judge.run_grounding_judge(bundle, {"C1": {"dimension": "testing", "text": "a | b"}}, "judge-x"))

    assert verdict.citation_verdicts[0].label == "grounded"


def test_the_hosted_judge_is_never_flagged_as_truncated(monkeypatch) -> None:
    seen: list = []
    _stub_llm(monkeypatch, prompt_tokens=9_900, num_ctx_seen=seen)

    bundle = ArtifactBundle(team_id="t", sprint_id="s")
    asyncio.run(judge.run_grounding_judge(bundle, {"C1": {"dimension": "testing", "text": "a | b"}}, "gpt-4o-mini", "openai"))

    assert seen == [None]  # no Ollama num_ctx to compare against


# ---------------------------------------------------------------- shared config


def test_one_judge_model_default_for_production_and_research(monkeypatch) -> None:
    monkeypatch.delenv("SPRINTSIGHT_JUDGE_MODEL", raising=False)
    assert configured_judge_model() == DEFAULT_JUDGE_MODEL == "sprintsight-judge-phi"

    monkeypatch.setenv("SPRINTSIGHT_JUDGE_MODEL", "")
    assert configured_judge_model() == DEFAULT_JUDGE_MODEL  # an empty variable does not mean "no judge"

    monkeypatch.setenv("SPRINTSIGHT_JUDGE_MODEL", "other-judge")
    assert configured_judge_model() == "other-judge"


def test_production_and_research_entry_points_agree_on_the_default() -> None:
    # In a fresh interpreter with the variable unset. Reloading the modules inside the test run
    # replaced their classes (JudgeContextTooSmall, ...) and made later tests depend on order.
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {key: value for key, value in os.environ.items() if key != "SPRINTSIGHT_JUDGE_MODEL"}
    env["MLFLOW_DISABLE_AGENT_HINT"] = "1"
    code = (
        "from judges import citation_ground_custom_judge as a, custom_llm_judge as b;"
        "from research.eval import mlflow_judge_eval as c;"
        "print(a.JUDGE_MODEL, b.DEFAULT_JUDGE_MODEL, c.DEFAULT_JUDGE_MODEL)"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent,
                          env=env, capture_output=True, text=True, timeout=120, check=True)

    assert done.stdout.split() == ["sprintsight-judge-phi"] * 3
