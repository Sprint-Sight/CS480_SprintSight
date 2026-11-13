import json
import sys

import pytest
from research import compare_runs
from services import audit_logger


def _answer(score: int, justification: str = "Solid work.", citations: list | None = None) -> str:
    return json.dumps({
        "score": score,
        "justification": justification,
        "evidence_citations": citations if citations is not None else [{"file": "app.py", "line": 3}],
    })


def _record(request_id: str, dimension: str, content: str, bundle_hash: str = "h1") -> None:
    completion = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    audit_logger.write_audit_record({
        "request_id": request_id, "dimension": dimension, "model": "m", "bundle_hash": bundle_hash,
        "request": {"messages": []}, "raw_response": json.dumps(completion),
    })


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_logger, "AUDIT_LOG_DIR", tmp_path)
    return tmp_path


def _write_markers(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_identical_runs_including_retries(audit_dir):
    _record("a1", "testing", "not json")          # first attempt, retried
    _record("a1", "testing", _answer(6))
    _record("b1", "testing", "not json")
    _record("b1", "testing", _answer(6))
    # Records with no model answer (client errors, grounding notes) are skipped.
    audit_logger.write_audit_record({"request_id": "b1", "dimension": "testing", "error": "timeout"})

    runs = [compare_runs.load_run_answers(audit_dir, {"a1"}), compare_runs.load_run_answers(audit_dir, {"b1"})]
    result = compare_runs.compare_runs(runs)["testing"]
    assert result["attempts"] == [2, 2]
    assert result["identical"] is True
    assert result["score_changed"] is False
    assert result["same_evidence"] is True


def test_score_change_and_partial_citation_overlap(audit_dir):
    _record("a1", "cicd", _answer(7, "Pipeline runs tests.", [{"file": "ci.yml"}, {"file": "Dockerfile"}]))
    _record("b1", "cicd", _answer(5, "Pipeline runs no tests.", [{"file": "ci.yml"}]))

    runs = [compare_runs.load_run_answers(audit_dir, {"a1"}), compare_runs.load_run_answers(audit_dir, {"b1"})]
    result = compare_runs.compare_runs(runs)["cicd"]
    assert result["identical"] is False
    assert result["scores"] == [7, 5]
    assert result["score_changed"] is True
    assert result["citation_overlap"] == [0.5]
    assert 0.5 < result["text_similarity"][0] < 1


def test_changed_evidence_is_flagged(audit_dir):
    _record("a1", "documentation", _answer(6), bundle_hash="before-resync")
    _record("b1", "documentation", _answer(6), bundle_hash="after-resync")
    runs = [compare_runs.load_run_answers(audit_dir, {"a1"}), compare_runs.load_run_answers(audit_dir, {"b1"})]
    assert compare_runs.compare_runs(runs)["documentation"]["same_evidence"] is False


def test_cli_exits_nonzero_when_a_score_changes(audit_dir, monkeypatch, capsys):
    _record("a1", "testing", _answer(6))
    _record("b1", "testing", _answer(4))
    markers = audit_dir / "request_markers.jsonl"
    _write_markers(markers, [
        {"run_id": "run-aaaa", "request_id": "a1", "model": "m", "team_id": "t", "sprint_id": "s", "duration_ms": 1000},
        {"run_id": "run-bbbb", "request_id": "b1", "model": "m", "team_id": "t", "sprint_id": "s", "duration_ms": 500},
    ])
    monkeypatch.setattr(sys, "argv", [
        "compare_runs", "run-a", "run-b", "--markers", str(markers), "--audit-dir", str(audit_dir),
    ])
    with pytest.raises(SystemExit) as exit_info:
        compare_runs.main()
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "| testing | 1/1 | yes | no | 6/4 CHANGED |" in output
    assert "SCORES CHANGED" in output


def test_resolve_run_requires_a_unique_prefix():
    assert compare_runs.resolve_run("401b", ["401ba684", "aa2a6d82"]) == "401ba684"
    with pytest.raises(SystemExit):
        compare_runs.resolve_run("", ["401ba684", "aa2a6d82"])
