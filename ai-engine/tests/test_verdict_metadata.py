import json

from evaluation.judges.verdict_metadata import (
    MAX_JSON_CHARS,
    METADATA_KEY,
    TRUNCATED_KEY,
    citation_verdicts_metadata,
)


def row(i, label="hallucinated"):
    return {"citation_id": f"C{i}", "dimension": "testing", "claim": "abc123 | Added tests",
            "label": label, "severity": "major_misattribution", "reasoning": "r" * 1000}

def test_keeps_only_non_grounded_rows_with_claims_and_caps_fields():
    meta = citation_verdicts_metadata([row(1), row(2, "grounded")])
    data = json.loads(meta[METADATA_KEY])
    assert [d["citation_id"] for d in data] == ["C1"]
    assert data[0]["claim"] == "abc123 | Added tests"
    assert len(data[0]["reasoning"]) == 400
    assert meta[TRUNCATED_KEY] == "false"

def test_drops_rows_past_the_size_cap_and_says_so():
    meta = citation_verdicts_metadata([row(i) for i in range(200)])
    assert len(meta[METADATA_KEY]) <= MAX_JSON_CHARS
    assert meta[TRUNCATED_KEY] == "true"
    assert json.loads(meta[METADATA_KEY])[0]["citation_id"] == "C0"  # dropped from the end

def test_all_grounded_gives_an_empty_list():
    meta = citation_verdicts_metadata([row(1, "grounded")])
    assert json.loads(meta[METADATA_KEY]) == [] and meta[TRUNCATED_KEY] == "false"