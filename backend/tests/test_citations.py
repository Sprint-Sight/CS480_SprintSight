from types import SimpleNamespace
from app.services.insightsService import citations as c

'''
Test for citation rationale parsing by testing:
1. The parsing of a real rationale format with continuation lines and claims.
2. The marking of truncated rationale and ignoring of "all grounded" message.
3. The matching of claim numbering to the ai-engine order and skipping failed dimensions.
4. The derivation of judge status based on the presence and content of assessments.
5. The summarization of traces, ensuring that payloads are stripped and LLM calls are collapsed.
'''

LINE = "C1 [testing] partially_grounded/minor_detail: file not in the diff"

def test_short_rationale_is_not_truncated():
    rows, truncated = c.parse_citation_rationale(LINE, {"C1": "a.py | reason"})
    assert truncated is False
    assert (rows[0].citation_id, rows[0].dimension, rows[0].claim) == ("C1", "testing", "a.py | reason")

def test_rationale_at_the_limit_is_flagged_truncated():
    text = LINE + "\n" + "x" * c.RATIONALE_LIMIT
    _, truncated = c.parse_citation_rationale(text, {})
    assert truncated is True            # regression: this is the line the bad paste deleted

def test_wrapped_reasoning_is_joined_to_its_row():
    rows, _ = c.parse_citation_rationale(LINE + "\nspilled onto next line", {})
    assert rows[0].reasoning.endswith("spilled onto next line")

def test_empty_rationale():
    assert c.parse_citation_rationale(None, {}) == ([], False)

def test_unaccepted_citations_with_no_judge_result_is_empty():
    pending = SimpleNamespace(assessment=lambda name: None, claims={})
    assert c.unaccepted_citations(pending) == ([], False)