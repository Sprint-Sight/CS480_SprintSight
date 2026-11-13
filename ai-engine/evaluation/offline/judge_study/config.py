"""Judge endpoint configuration (Part 0): judge-model constants, MLflow's openai endpoint
for local Ollama, the brace guard, the single judge call and the judge-independence check.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

from llmops import experiments

from evaluation.judges.config import configured_judge_model
from evaluation.offline.provenance import model_family

log = logging.getLogger(__name__)


# The 1-5 scale is used for every LLM-judged dimension. It is deliberately
# coarser than the 1-10 scale the candidate models grade students on: a judge
# asked to discriminate ten levels of "faithfulness" produces noise, and the
# meta-evaluation in Part 5 needs enough mass per cell for a kappa to mean
# anything. Five ordered levels with written anchors is the standard
# compromise in the rubric-design literature.
RUBRIC_MIN = 1
RUBRIC_MAX = 5

JUDGE_EXPERIMENT = os.getenv("SPRINTSIGHT_JUDGE_EXPERIMENT", experiments.JUDGE_STUDY)

# The judge MUST come from a different model family than the candidates
# under test (models/Modelfile.*, schemas/modelname.py); otherwise a judge
# grading its own family introduces self-preference bias -- a judge's measured
# tendency to prefer text from its own family -- that becomes indistinguishable
# from real quality.
#
# sprintsight-judge-phi (phi4:14b) is the default because the existing judge code reaches for
# the phi family (`SPRINTSIGHT_JUDGE_MODEL` defaults to "sprintsight-judge-phi"
# in evaluation/judges/config.py), it is not a llama derivative, and at Q4 it
# fits alongside a 3B candidate on a 24 GB card. `assert_judge_independence`
# enforces the family rule at run time rather than trusting this default.
#
#   sprintsight-judge-phi           # phi4:14b, ~9 GB; created by compose and the HPC job
#   qwen2.5:14b-instruct            # alternative, also non-llama
# Shared with the production judge (evaluation/judges/config.py). The default used to differ
# ("phi4:14b" here, "sprintsight-judge-phi" there) for the SAME environment variable, so an
# unset variable meant a different judge per entry point. sprintsight-judge-phi IS phi4:14b,
# built from models/Modelfile.phi.
DEFAULT_JUDGE_MODEL = configured_judge_model()

# Opt-out for the family rule. Exists because a reviewer may legitimately want
# to MEASURE self-preference bias by deliberately judging within a family;
# it is not there to make a convenient judge acceptable.
ALLOW_SAME_FAMILY_JUDGE = os.getenv("SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE", "") == "1"

# Greedy decoding plus a fixed seed: the judge is an instrument, and an
# instrument that gives a different reading each time it is used cannot
# calibrate anything. Part 7 then deliberately breaks this in order to
# MEASURE how much of our signal depends on it.
JUDGE_SEED = int(os.getenv("SPRINTSIGHT_JUDGE_SEED", "7"))

# max_tokens must sit far above MLflow's 200-token default: the CoT protocol
# asks for an evidence scan and a per-test anchor check before the score, and
# a truncated response loses the score field entirely.
JUDGE_MAX_TOKENS = int(os.getenv("SPRINTSIGHT_JUDGE_MAX_TOKENS", "1200"))

# How much of the candidate's evidence view to show the judge.
#
# 32000 chars is roughly 8k tokens, which leaves room alongside the rubric,
# the few-shot exemplars and the stage-one audit inside a 16k-context judge
# such as phi4:14b. It is sized against what has to fit: the union of
# per-dimension commit samples measured 64-89 commits on the real sprints,
# which renders at well under this, so truncation should be the exception
# rather than the rule.
#
# Raising this is NOT the way to fix a truncated bundle -- the full real-sprint
# bundle renders at up to 2.4 MB, so no budget makes it fit. The fix is to show
# the candidate's sampled view instead; see candidate_visible_commits.
JUDGE_BUNDLE_CHAR_BUDGET = int(os.getenv("SPRINTSIGHT_JUDGE_BUNDLE_CHARS", "32000"))


# Context window requested of the judge, as Ollama's `options.num_ctx`.
#
# This must be set explicitly. Ollama applies its own small default (a few
# thousand tokens) unless a Modelfile or the request says otherwise, and it
# truncates an over-long prompt SILENTLY -- no error, no warning. Every
# character budget in this module would be meaningless if the server quietly
# dropped the end of the bundle, and the symptom would be the judge calling
# real citations fabricated: exactly the bug candidate_visible_commits exists
# to fix. llm_client.py takes the same precaution via _request_extra_body.
#
# 32768 covers the 32000-char bundle budget plus the rubric, the exemplars
# and the stage-one audit with room to spare (chars // 4 is the usual rough
# token estimate). Keep it at or below the judge's real ceiling: phi4:14b is
# 16k, qwen2.5:14b-instruct is 32k. Set SPRINTSIGHT_JUDGE_NUM_CTX to 16384
# for a 16k judge, or 0 to omit the override entirely and let Ollama decide.
JUDGE_NUM_CTX = int(os.getenv("SPRINTSIGHT_JUDGE_NUM_CTX", "16384"))  # phi4:14b (the default judge) was trained for 16384; Ollama clamps more


def judge_parameters(temperature: float = 0.0, seed: int | None = None) -> dict[str, Any]:
    """Decoding parameters forwarded verbatim to the judge's chat endpoint.

    ``response_format`` is included because local models wrap JSON in
    markdown fences often enough to matter, and a fenced response fails both
    of MLflow's parse paths. Ollama honours OpenAI's ``json_object`` mode, and
    MLflow passes unrecognised parameters straight through to the payload --
    verified for both ``response_format`` and ``options``.
    """
    parameters: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": JUDGE_MAX_TOKENS,
        "top_p": 1.0,
        "seed": JUDGE_SEED if seed is None else seed,
        "response_format": {"type": "json_object"},
    }
    if JUDGE_NUM_CTX > 0:
        parameters["options"] = {"num_ctx": JUDGE_NUM_CTX}
    return parameters


def configure_judge_endpoint(
    judge_model: str = DEFAULT_JUDGE_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Point MLflow's ``openai:/`` provider at local Ollama; return the URI.

    MLflow resolves ``openai:/<model>`` through its gateway OpenAIProvider,
    which reads ``OPENAI_API_BASE`` / ``OPENAI_API_KEY`` from the environment.
    Ollama's ``/v1`` endpoint is OpenAI-compatible, so setting those two
    variables is the entire integration: no deployment server, no gateway
    config file, and the judge weights stay on hardware we control -- which
    is also what lets a reader reproduce the study.

    Call before ``mlflow.evaluate``. The provider is constructed per call, so
    a later change to these variables is picked up.
    """
    resolved_base = base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    if not resolved_base.rstrip("/").endswith("/v1"):
        resolved_base = resolved_base.rstrip("/") + "/v1"
    os.environ["OPENAI_API_BASE"] = resolved_base
    # Ollama ignores the key, but the OpenAI wire format requires one.
    os.environ["OPENAI_API_KEY"] = api_key or os.getenv("OLLAMA_API_KEY") or "ollama"
    uri = f"openai:/{judge_model}"
    log.info("Judge endpoint configured: %s via %s", uri, resolved_base)
    return uri


_BRACE = re.compile(r"[{}]")


def _assert_brace_free(text: str, where: str) -> str:
    """Reject template-time text containing braces. See module docstring (1).

    Not defensive paranoia about a hypothetical: one brace here produces an
    empty judge prompt and a full column of None scores that looks exactly
    like "the judge could not parse the output", which is the hardest class
    of bug to notice in an eval pipeline.
    """
    if _BRACE.search(text):
        raise ValueError(
            f"{where} contains a literal brace. MLflow's PromptTemplate would "
            "treat it as a format placeholder and silently emit an EMPTY judge "
            "prompt, so every score would come back None. Rewrite the text "
            "without braces -- describe JSON keys in prose instead."
        )
    return text


def _strip_braces(text: str) -> str:
    """Sanitise rendered text that will be embedded at template time."""
    return _BRACE.sub("", text)


#
# Absolute 1-5 scoring has a known weakness: local judges compress onto the
# middle of the scale, so two models that differ materially can both land on
# 3. Pairwise comparison recovers that resolution -- but introduces position
# bias, the well-documented tendency of an LLM judge to prefer whichever
# candidate it was shown first, regardless of content.
#
# Every comparison here is therefore run TWICE with the order swapped, and a
# verdict only counts if it survives the swap. Disagreement between the two
# orders is not discarded quietly: it is counted and reported as
# `position_bias_rate`, which is a direct, honest measure of how much of the
# judge's preference is an artifact of presentation. A pairwise study that
# does not report this number is not evidence of anything.


def _judge_call(
    prompt: str,
    judge_uri: str,
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Single raw judge completion.

    Routed through the same ``score_model_on_payload`` that
    ``make_genai_metric`` uses internally, rather than a separate OpenAI
    client, so Parts 6 and 7 cannot diverge from the transport the headline
    metrics were produced with -- and so the stub judge in Part 10 covers all
    three paths with one patch.
    """
    from mlflow.metrics.genai import model_utils

    return model_utils.score_model_on_payload(
        judge_uri,
        prompt,
        dict(parameters or judge_parameters()),
        None,
        None,
        "llm/v1/chat",
    )


def assert_judge_independence(
    judge_model: str,
    candidate_models: Sequence[str],
    *,
    allow_same_family: bool = ALLOW_SAME_FAMILY_JUDGE,
) -> dict[str, Any]:
    """Refuse to judge candidates from the judge's own model family.

    Self-preference bias is a measured property of LLM judges: a judge scores
    text from its own family higher than blinded human raters do. When judge
    and candidate share a family, a "better" score is not separable from "more
    like me", and the comparison cannot support a claim about quality.

    This is enforced rather than documented because the failure is silent and
    the convenient choice is always the wrong one -- the judge tag that is
    already pulled is usually a sibling of the candidates. Set
    SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE=1 only to deliberately MEASURE the
    bias, and the override is recorded as an MLflow param either way.

    Returns a provenance dict for logging. Raises when the rule is violated
    and no override is set. An unreachable Ollama downgrades to a warning:
    unknown provenance must not block a run, but it must not be silent.
    """
    judge_family, judge_parent = model_family(judge_model)
    info: dict[str, Any] = {
        "judge_family": judge_family or "unknown",
        "judge_parent": judge_parent or "unknown",
        "same_family_override": allow_same_family,
    }

    if judge_family is None:
        log.warning(
            "Could not determine the family of judge '%s'; the "
            "self-preference check could not run. Record the judge's "
            "provenance manually in the report.",
            judge_model,
        )
        info["independence"] = "unverified"
        return info

    clashes: list[str] = []
    for candidate in sorted(set(candidate_models)):
        family, parent = model_family(candidate)
        if family is None:
            continue
        # Same declared family, or the judge IS the candidate's base model.
        if family == judge_family or (parent and parent.split(":")[0] == judge_model.split(":")[0]):
            clashes.append(f"{candidate} (family={family}, parent={parent})")

    info["clashing_candidates"] = clashes
    info["independence"] = "ok" if not clashes else "violated"

    if clashes and not allow_same_family:
        raise RuntimeError(
            f"Judge '{judge_model}' (family={judge_family}) shares a model family "
            f"with {len(clashes)} candidate(s) under test: {', '.join(clashes)}. "
            "Self-preference bias makes these scores uninterpretable as quality. "
            "Use a judge from another family -- the default sprintsight-judge-phi or "
            "`ollama pull qwen2.5:14b-instruct` -- or set "
            "SPRINTSIGHT_ALLOW_SAME_FAMILY_JUDGE=1 if you are deliberately "
            "measuring the bias itself."
        )
    if clashes:
        log.warning(
            "SAME-FAMILY JUDGING IS ACTIVE for %s. Scores are confounded with "
            "self-preference bias and must be labelled as such in the report.",
            ", ".join(clashes),
        )
    return info
