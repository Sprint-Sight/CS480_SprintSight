"""
services/grounding.py

Shared logic for verifying that LLM-generated evidence citations actually
trace back to the real, ingested student artifact data — rather than to
example/fixture text, or to plausible-sounding but fabricated content.

Used in two places:
  - schemas/rubrics_dimension_score.py: a field_validator that runs DURING
    generation, with the bundle passed in via instructor's validation_context.
    When it raises ValueError, instructor automatically re-asks the model to
    fix ungrounded citations, using the max_retries budget you already pay for.
  - services/llm_client.py: a hard backstop that runs AFTER generation, in
    case no validation_context was supplied, or retries were exhausted and
    the model still didn't self-correct.

Kept in its own module (rather than inside llm_client.py or the schema file)
specifically to avoid a circular import: llm_client.py imports
RubricDimensionScore from the schema module, so the schema module can't also
import from llm_client.py.
"""
from __future__ import annotations
import json
import re

# Matches identifier-like substrings: commit SHAs, JIRA keys ("ENG-123"),
# filenames, metric names — the kind of hard anchor a real citation should
# contain, and a fabricated citation usually won't reproduce exactly.
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{3,}")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _collect_leaf_values(node: object, out: list[str]) -> None:
    # Walk only VALUES, never dict keys — schema field names like "commits"
    # or "jira_tickets" would otherwise contaminate the corpus and let a
    # citation containing the word "commit" match against the "commits" key.
    if isinstance(node, dict):
        for value in node.values():
            _collect_leaf_values(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_leaf_values(item, out)
    elif node is not None:
        out.append(str(node))


def _build_value_corpus(bundle_data: str) -> str:
    try:
        parsed = json.loads(bundle_data)
    except (json.JSONDecodeError, TypeError):
        # Not JSON for some reason — fall back to raw text rather than crash.
        return _normalize(bundle_data)
    values: list[str] = []
    _collect_leaf_values(parsed, values)
    return _normalize(" ".join(values))


def find_ungrounded_citations(bundle_data: str, citations: list[str]) -> list[str]:
    """
    Returns the subset of `citations` that cannot be traced back to
    `bundle_data` (the actual serialized ArtifactBundle sent to the model) —
    which is exactly the fingerprint of a hallucinated citation, regardless
    of whether it was copied from an example or fabricated outright.

    A citation is considered grounded if EITHER:
      (a) it appears near-verbatim in the bundle's data VALUES
          (whitespace/case-normalized), or
      (b) it contains at least one identifier-like token (a SHA, ticket key,
          filename, etc.) that appears verbatim among those values.
    (a) alone is too strict — the model may rephrase slightly around a real
    citation. (b) alone is too loose — a common short word could coincidentally
    match. Requiring one or the other balances precision and recall.

    The corpus is built from data VALUES only, not the raw JSON text — schema
    field names (e.g. "commits", "jira_tickets") must never count as evidence,
    or placeholder citations like "commit 1" would trivially match against the
    literal key name "commits" and pass.
    """
    corpus = _build_value_corpus(bundle_data)
    ungrounded = []
    for citation in citations:
        norm_citation = _normalize(citation)
        if norm_citation and norm_citation in corpus:
            continue
        tokens = _TOKEN_PATTERN.findall(citation)
        if any(_normalize(tok) in corpus for tok in tokens):
            continue
        ungrounded.append(citation)
    return ungrounded


def ensure_grounded_citations(bundle_data: str, citations: list[str]) -> None:
    """Raises ValueError if any citation isn't traceable to bundle_data."""
    ungrounded = find_ungrounded_citations(bundle_data, citations)
    if ungrounded:
        raise ValueError(
            "Ungrounded evidence citations detected — these do not appear in "
            "the student artifact bundle and look fabricated or copied from "
            f"example text instead of real evidence: {ungrounded!r}"
        )