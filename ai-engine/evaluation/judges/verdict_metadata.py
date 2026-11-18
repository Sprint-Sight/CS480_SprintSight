import json

'''
Structured copy of citation judge's non-grounded verdicts (under AI insights)

The rationale text is capped at 2000 chars; this metatdata keeps every 
non-grounded verdict with its claim. 
MLflow assessment metadata values must be strings
'''

METADATA_KEY = "sprintsight.citation_verdicts"
TRUNCATED_KEY = "sprintsight.citation_verdicts_truncated"
MAX_JSON_CHARS = 16_000
MAX_FIELD_CHARS = 400

def citation_verdicts_metadata(rows: list[dict]) -> dict[str, str]:
    keep = [
        {
            "citation_id": r["citation_id"],
            "dimension": r["dimension"],
            "claim": str(r.get("claim", ""))[:MAX_FIELD_CHARS],
            "label": r["label"],
            "severity": r["severity"],
            "reasoning": str(r.get("reasoning", ""))[:MAX_FIELD_CHARS],
        }
        for r in rows
        if r.get("label") != "grounded"
    ]
    truncated = False
    payload = json.dumps(keep, ensure_ascii=False)
    while keep and len(payload) > MAX_JSON_CHARS:  # drop rows from the end until it fits
        keep.pop()
        truncated = True
        payload = json.dumps(keep, ensure_ascii=False)
    return {METADATA_KEY: payload, TRUNCATED_KEY: str(truncated).lower()}