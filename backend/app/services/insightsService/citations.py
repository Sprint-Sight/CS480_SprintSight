"""Citations the judge did not fully accept.

Today the ai-engine writes them only into the rationale text (non-grounded rows, cut at
2000 chars, no claim text). Tier 2 adds a structured copy in assessment metadata; this
module prefers that and falls back to parsing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.services.insightsService.trace_summary import TraceSummary

RATIONALE_LIMIT = 2000
METADATA_KEY = "sprintsight.citation_verdicts"
# One line per citation, as written by the ai-engine's llm_judge_citation_grounding:
#   C7 [documentation] partially_grounded/minor_detail: <reasoning>
_LINE = re.compile(r"^(C\d+) \[([a-z_]+)\] ([a-z_]+)/([a-z_]+): (.*)$")

@dataclass(frozen=True)
class CitationVerdictRow:
    citation_id: str
    dimension: str
    claim: str | None
    verdict: str
    severity: str
    reasoning: str

def parse_citation_rationale(
    text: str | None, claims: dict[str, str]
) -> tuple[list[CitationVerdictRow], bool]:
    """(rows, truncated). `truncated` is True when the rationale hit the ai-engine's cut-off."""
    if not text:
        return [], False
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        match = _LINE.match(line)
        if match:
            cid, dimension, verdict, severity, reasoning = match.groups()
            rows.append(
                {
                    "citation_id": cid,
                    "dimension": dimension,
                    "verdict": verdict,
                    "severity": severity,
                    "reasoning": reasoning,
                }
            )
        elif rows and line:  # a reasoning that spilled onto another line
            rows[-1]["reasoning"] += " " + line
    truncated = len(text) >= RATIONALE_LIMIT
    return [CitationVerdictRow(claim=claims.get(r["citation_id"]), **r) for r in rows], truncated

def unaccepted_citations(summary: TraceSummary) -> tuple[list[CitationVerdictRow], bool]:
    primary = summary.assessment("citation_hallucination_rate")
    if primary and primary.metadata.get(METADATA_KEY):
        try:
            data = json.loads(primary.metadata[METADATA_KEY])
            return [
                CitationVerdictRow(
                    citation_id=d["citation_id"],
                    dimension=d["dimension"],
                    claim=d.get("claim") or summary.claims.get(d["citation_id"]),
                    verdict=d["label"],
                    severity=d["severity"],
                    reasoning=d["reasoning"],
                )
                for d in data
                if d.get("label") != "grounded"
            ], False
        except (ValueError, KeyError, TypeError):
            pass  # fall back to the rationale text
    for name in ("citation_hallucination_rate", "citation_severity_weighted_rate"):
        assessment = summary.assessment(name)
        if assessment and assessment.rationale:
            return parse_citation_rationale(assessment.rationale, summary.claims)
    return [], False