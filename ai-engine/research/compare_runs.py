"""Check that a performance change did not change grading output.

Compares two or more assessment runs of the same sprint, dimension by
dimension, using what the AI engine already records:
  - audit_logs/request_markers.jsonl: which requests belong to which run
    (run_id = the MLflow run of that assessment), and
  - audit_logs/llm_*.txt: the exact evidence hash and the model's raw answer
    for every request, retries included.

Grading runs at temperature 0, so a change that only affects speed (CPU
threads, keep-alive, ...) should give byte-identical answers. Where answers
differ, the report shows whether the score moved, how many cited items the
runs share, and how similar the justifications are. "same evidence = no"
means the inputs changed between runs (e.g. the repo was re-synced), so the
answers are not expected to match.

Usage (from ai-engine/):

    python -m research.compare_runs --list
    python -m research.compare_runs aa2a6d82 401ba684

Exit status is 1 if any dimension's score differs, so this can gate a change.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_METADATA_HEADER = "METADATA\n--------\n"
_REQUEST_HEADER = "\n\nINPUT SENT TO OLLAMA\n"
_RESPONSE_HEADER = "RAW OUTPUT FROM OLLAMA\n----------------------\n"
_ERROR_HEADER = "\n\nCLIENT ERROR\n"


def load_markers(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def list_runs(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary per run_id, oldest first."""
    runs: dict[str, dict[str, Any]] = {}
    for marker in markers:
        run = runs.setdefault(str(marker.get("run_id")), {
            "run_id": str(marker.get("run_id")), "started_at": marker.get("started_at"),
            "model": marker.get("model"), "team_id": marker.get("team_id"), "sprint_id": marker.get("sprint_id"),
            "concurrency": marker.get("concurrency"), "requests": 0, "request_seconds": 0.0,
        })
        run["requests"] += 1
        run["request_seconds"] += (marker.get("duration_ms") or 0) / 1000
        run["finished_at"] = marker.get("finished_at")
    return list(runs.values())


def resolve_run(prefix: str, run_ids: list[str]) -> str:
    matches = [run_id for run_id in run_ids if run_id.startswith(prefix)]
    if len(matches) != 1:
        raise SystemExit(f"Run '{prefix}' matches {len(matches)} runs; use --list and give a longer prefix.")
    return matches[0]


def parse_answer_record(text: str) -> dict[str, Any] | None:
    """Metadata plus the model's answer text from one audit record; None for
    records without a model answer (client errors, citation-grounding notes)."""
    if _METADATA_HEADER not in text or _RESPONSE_HEADER not in text:
        return None
    metadata_text = text.split(_METADATA_HEADER, 1)[1].split(_REQUEST_HEADER, 1)[0]
    raw = text.split(_RESPONSE_HEADER, 1)[1].split(_ERROR_HEADER, 1)[0].strip()
    try:
        metadata = json.loads(metadata_text)
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None
    return {**metadata, "content": content}


def load_run_answers(audit_dir: Path, request_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """dimension -> every answer the model gave in this run, in order (the
    last one is the attempt that was accepted; earlier ones were retried)."""
    by_dimension: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(audit_dir.glob("llm_*.txt")):
        record = parse_answer_record(path.read_text(encoding="utf-8"))
        if record and record.get("request_id") in request_ids:
            by_dimension.setdefault(str(record.get("dimension")), []).append(record)
    for answers in by_dimension.values():
        answers.sort(key=lambda r: str(r.get("logged_at")))
    return by_dimension


def _parsed(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _citation_keys(answer: dict[str, Any]) -> set[str]:
    return {json.dumps(c, sort_keys=True) for c in answer.get("evidence_citations") or []}


def _text(answer: dict[str, Any]) -> str:
    """Justification for rubric dimensions; the whole answer for sprint feedback."""
    if "justification" in answer:
        return str(answer["justification"])
    return json.dumps(answer, sort_keys=True)


def compare_dimension(runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """Compare one dimension's accepted answers across runs (first run = reference)."""
    finals = [answers[-1] for answers in runs]
    parsed = [_parsed(f["content"]) for f in finals]
    reference_citations = _citation_keys(parsed[0])
    overlaps, similarities = [], []
    for answer in parsed[1:]:
        citations = _citation_keys(answer)
        union = reference_citations | citations
        overlaps.append(round(len(reference_citations & citations) / len(union), 3) if union else 1.0)
        similarities.append(round(difflib.SequenceMatcher(None, _text(parsed[0]), _text(answer)).ratio(), 3))
    scores = [p.get("score") for p in parsed]
    return {
        "attempts": [len(answers) for answers in runs],
        "same_evidence": len({f.get("bundle_hash") for f in finals}) == 1,
        "identical": len({hashlib.sha256(f["content"].encode()).hexdigest() for f in finals}) == 1,
        "scores": scores,
        "score_changed": len(set(scores)) > 1,
        "citation_overlap": overlaps,
        "text_similarity": similarities,
    }


def compare_runs(per_run: list[dict[str, list[dict[str, Any]]]]) -> dict[str, dict[str, Any]]:
    dimensions = [d for d in per_run[0] if all(d in run for run in per_run)]
    return {d: compare_dimension([run[d] for run in per_run]) for d in dimensions}


def _verdict(results: dict[str, dict[str, Any]]) -> str:
    if all(r["identical"] for r in results.values()):
        return "IDENTICAL: every answer is byte-for-byte the same."
    if any(r["score_changed"] for r in results.values()):
        return "SCORES CHANGED: check the dimensions marked below before adopting this change."
    return "SCORES MATCH, wording differs: review the low-similarity dimensions."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="*", help="Run IDs (or unique prefixes); the first is the reference")
    parser.add_argument("--list", action="store_true", help="List recorded runs and exit")
    parser.add_argument("--markers", type=Path, default=Path("audit_logs/request_markers.jsonl"))
    parser.add_argument("--audit-dir", type=Path, default=Path("audit_logs"))
    args = parser.parse_args()

    markers = load_markers(args.markers)
    summaries = list_runs(markers)
    if args.list or len(args.runs) < 2:
        for run in summaries:
            print(
                f"{run['run_id'][:12]}  {str(run['started_at'])[:19]}  {run['model']}  sprint={run['sprint_id']}  "
                f"team={str(run['team_id'])[:8]}  concurrency={run['concurrency']}  "
                f"requests={run['requests']}  request_time={run['request_seconds']:.0f}s"
            )
        if not args.list:
            print("\nGive at least two run IDs to compare, e.g. python -m research.compare_runs <ref> <new>")
        return

    run_ids = [resolve_run(prefix, [s["run_id"] for s in summaries]) for prefix in args.runs]
    by_id = {s["run_id"]: s for s in summaries}
    if len({(by_id[r]["team_id"], by_id[r]["sprint_id"]) for r in run_ids}) > 1:
        print("WARNING: these runs graded different team/sprint combinations; answers will not match.\n")

    per_run = [
        load_run_answers(args.audit_dir, {m["request_id"] for m in markers if m.get("run_id") == run_id})
        for run_id in run_ids
    ]
    results = compare_runs(per_run)

    for run_id in run_ids:
        run = by_id[run_id]
        print(f"run {run_id[:12]}  {run['model']}  concurrency={run['concurrency']}  request_time={run['request_seconds']:.0f}s")
    print()
    header = ["dimension", "attempts", "same evidence", "identical", "scores", "citation overlap", "text similarity"]
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for dimension, r in results.items():
        cells = [
            dimension, "/".join(map(str, r["attempts"])), "yes" if r["same_evidence"] else "NO",
            "yes" if r["identical"] else "no",
            "/".join("-" if s is None else str(s) for s in r["scores"]) + (" CHANGED" if r["score_changed"] else ""),
            "/".join(map(str, r["citation_overlap"])), "/".join(map(str, r["text_similarity"])),
        ]
        print("| " + " | ".join(cells) + " |")
    print("\n" + _verdict(results))
    if any(r["score_changed"] for r in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
