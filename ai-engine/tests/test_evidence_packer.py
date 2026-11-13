from datetime import UTC, datetime, timedelta

import pytest
from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from schemas.artifact_bundle import ArtifactBundle
from schemas.rubrics_dimension_score import ModelOutput
from services import llm_client
from services.evidence_packer import (
    estimate_tokens,
    file_category,
    is_noise_path,
    pack_dimension_evidence,
)
from services.grounding import resolve_citations

APP_PY = "\n".join(
    ["import os", "", "class Service:", "    def run(self):", "        return 1"]
    + [f"# filler {n}" for n in range(6, 41)]
) + "\n"
TEST_PY = "def test_run():\n    assert Service().run() == 1\n"
README = "# Project\n\nHow to run it.\n"
DIFF = "@@ -0,0 +1,5 @@\n+import os\n+\n+class Service:\n+    def run(self):\n+        return 1\n"
EDIT_DIFF = "@@ -3,3 +3,4 @@ class Service:\n     def run(self):\n-        return 0\n+        value = 1\n+        return value\n"


def _commit(n: int, author: str, message: str, files: list[dict]) -> dict:
    return {
        "sha": f"{n:07x}" + "a" * 33,
        "author": author,
        "message": message,
        "timestamp": (datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=n)).isoformat(),
        "lines_added": sum(f.get("lines_added", 0) for f in files),
        "lines_deleted": sum(f.get("lines_deleted", 0) for f in files),
        "files_changed": files,
    }


def _bundle(commit_count: int = 4) -> dict:
    commits = [
        _commit(1, "alice", "Add service", [
            {"filename": "src/app.py", "change_type": "added", "lines_added": 5, "diff": DIFF},
        ]),
        _commit(2, "bob", "Return computed value", [
            {"filename": "src\\app.py", "change_type": "modified", "lines_added": 2,
             "lines_deleted": 1, "diff": EDIT_DIFF},
        ]),
        _commit(3, "carol", "Add tests", [
            {"filename": "tests/test_app.py", "change_type": "added", "lines_added": 2, "diff": "@@ -0,0 +1,2 @@\n+def test_run():\n+    assert True\n"},
        ]),
    ]
    commits += [
        _commit(n, "dave", f"Tweak {n}", [{"filename": "src/app.py", "lines_added": 1}])
        for n in range(4, commit_count + 1)
    ]
    return {
        "team_id": "team-1",
        "sprint_id": "sprint-1",
        "commits": commits,
        "jira_tickets": [
            {"ticket_id": "ENG-7", "summary": "Build service", "status": "Done", "issue_type": "Task"},
        ],
        "collaboration_metrics": {"completion_percent": 80},
        "artifact_metrics": {},
        "repo_snapshot": {
            "head_sha": commits[-1]["sha"],
            "files": [
                {"path": "src/app.py", "line_count": 40, "content": APP_PY},
                {"path": "src/layout/view.py", "line_count": 1, "content": "def view():\n"},
                {"path": "tests/test_app.py", "line_count": 2, "content": TEST_PY},
                {"path": "README.md", "line_count": 3, "content": README},
                {"path": ".github/workflows/ci.yml", "line_count": 1, "content": "on: push\n"},
            ],
        },
        "instructor_expectations": "No instructor guidance provided.",
    }


FIELDS = llm_client._DIMENSION_ARTIFACT_FIELDS


def test_noise_filter_matches_whole_path_segments():
    assert not is_noise_path("frontend/src/layout/Header.tsx")  # contains "out/"
    assert not is_noise_path("src/checkout/cart.py")
    assert is_noise_path("frontend/node_modules/react/index.js")
    assert is_noise_path("ios/Pods/Thing.swift")
    assert is_noise_path("web/package-lock.json")
    assert is_noise_path("static/app.min.js")


@pytest.mark.parametrize(("path", "category"), [
    ("tests/test_app.py", "test"),
    ("src/main/java/com/x/UserServiceTest.java", "test"),
    ("web/src/App.test.tsx", "test"),
    ("README.md", "docs"),
    ("docs/setup.txt", "docs"),
    (".github/workflows/ci.yml", "cicd"),
    ("backend/Dockerfile", "cicd"),
    ("src/app.py", "source"),
    ("assets/logo.png", None),
])
def test_file_category(path, category):
    assert file_category(path) == category


def test_ledger_lists_every_commit_when_it_fits():
    packed = pack_dimension_evidence(_bundle(200), "collaboration", FIELDS["collaboration"], 20000)
    assert packed.stats.commits_listed == packed.stats.commits_total == 200
    assert len(packed.index.commit_shas) == 200


def test_ledger_falls_back_to_relevant_subset_under_a_small_budget():
    packed = pack_dimension_evidence(_bundle(400), "testing", FIELDS["testing"], 3000)
    assert packed.stats.ledger_format == "compact-subset"
    assert 0 < packed.stats.commits_listed < 400
    # The test-touching commit is the most relevant one and must survive.
    assert _bundle()["commits"][2]["sha"] in packed.index.commit_shas
    assert "still counted in the computed facts" in packed.text


@pytest.mark.parametrize("budget", [1500, 4000, 12000])
@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_packed_text_stays_within_budget(dimension, budget):
    packed = pack_dimension_evidence(_bundle(300), dimension, FIELDS[dimension], budget)
    assert estimate_tokens(packed.text) <= budget


def test_head_files_and_diffs_carry_line_numbers_and_anchors():
    packed = pack_dimension_evidence(_bundle(), "code_quality", FIELDS["code_quality"], 12000)
    assert "=== FILE src/app.py (lines 1-40 of 40) | cite as src/app.py:L1-L40" in packed.text
    assert "   3| class Service:" in packed.text
    assert packed.index.head_lines["src/app.py"] == [(1, 40)]
    # The modifying diff (backslash path normalised) shows NEW line numbers:
    # context line 3, the removed line unnumbered, then added lines 4-5.
    bob_sha = _bundle()["commits"][1]["sha"]
    assert f"cite as src/app.py:L3-L5@{bob_sha[:7]}" in packed.text
    assert "     -         return 0" in packed.text
    assert "   4+         value = 1" in packed.text
    assert packed.index.diff_lines[("src/app.py", bob_sha)] == [(3, 5)]
    # Alice's diff only adds a file already shown in full, so it is skipped.
    assert ("src/app.py", _bundle()["commits"][0]["sha"]) not in packed.index.diff_lines


def test_dimensions_show_their_own_file_category():
    testing = pack_dimension_evidence(_bundle(), "testing", FIELDS["testing"], 12000)
    docs = pack_dimension_evidence(_bundle(), "documentation", FIELDS["documentation"], 12000)
    cicd = pack_dimension_evidence(_bundle(), "cicd", FIELDS["cicd"], 12000)
    assert set(testing.index.head_lines) == {"tests/test_app.py"}
    assert set(docs.index.head_lines) == {"README.md"}
    assert set(cicd.index.head_lines) == {".github/workflows/ci.yml"}


def test_requirements_gets_no_commit_evidence():
    packed = pack_dimension_evidence(_bundle(), "requirements", FIELDS["requirements"], 12000)
    assert "COMMIT LEDGER" not in packed.text
    assert '"ticket_id": "ENG-7"' in packed.text


def test_bundle_without_snapshot_or_diffs_still_packs_the_ledger():
    bundle = _bundle(50)
    bundle["repo_snapshot"] = None
    for commit in bundle["commits"]:
        for f in commit["files_changed"]:
            f.pop("diff", None)
    packed = pack_dimension_evidence(bundle, "code_quality", FIELDS["code_quality"], 12000)
    assert packed.stats.commits_listed == 50
    assert "No repository snapshot was supplied" in packed.text


def _index(dimension: str = "code_quality"):
    return pack_dimension_evidence(_bundle(), dimension, FIELDS[dimension], 12000).index


def _resolve(*identifiers: str, dimension: str = "code_quality"):
    citations = [{"identifier": i, "reason": "a reason that is long enough"} for i in identifiers]
    return resolve_citations(citations, _index(dimension))


def test_resolves_exact_and_narrowed_line_anchors():
    resolved, dropped, downgraded = _resolve("src/app.py:L3-L5")
    assert dropped == [] and downgraded == 0
    assert resolved[0] | {"reason": None} == {
        "reason": None, "kind": "file_lines", "identifier": "src/app.py:L3-L5",
        "file_path": "src/app.py", "line_start": 3, "line_end": 5,
        "commit_sha": _bundle()["repo_snapshot"]["head_sha"],
    }


def test_clamps_diff_ranges_to_the_lines_actually_shown():
    bob_sha = _bundle()["commits"][1]["sha"]
    resolved, _, _ = _resolve(f"src/app.py:L4-L90@{bob_sha[:7]}")
    assert resolved[0]["identifier"] == f"src/app.py:L4-L5@{bob_sha[:7]}"
    assert resolved[0]["kind"] == "diff_lines"
    assert resolved[0]["commit_sha"] == bob_sha


def test_prose_line_references_and_basenames_resolve():
    resolved, _, _ = _resolve("`app.py` lines 3 to 4")
    assert resolved[0]["identifier"] == "src/app.py:L3-L4"


def test_unseen_lines_and_unknown_commits_downgrade_to_file_level():
    resolved, dropped, downgraded = _resolve("src/app.py:L500-L510", "src/app.py:L3@ffffffff")
    assert dropped == [] and downgraded == 2
    assert [r["identifier"] for r in resolved] == ["src/app.py"]  # deduplicated


def test_commits_tickets_paths_and_metrics_resolve():
    resolved, dropped, _ = _resolve(
        f"commit {_bundle()['commits'][2]['sha'][:7]}",
        "ENG-7",
        "tests/test_app.py",
        "completion_percent 80",
        dimension="collaboration",
    )
    assert dropped == []
    assert [r["kind"] for r in resolved] == ["commit", "ticket", "file", "other"]
    # A dot-prefixed path from the file tree.
    resolved, _, _ = _resolve(".github/workflows/ci.yml", dimension="cicd")
    assert resolved[0]["identifier"] == ".github/workflows/ci.yml"


def test_evidence_a_dimension_was_not_shown_cannot_be_cited():
    # code_quality is never shown Jira tickets or collaboration metrics.
    resolved, dropped, _ = _resolve("ENG-7", "completion_percent 80")
    assert resolved == [] and len(dropped) == 2


def test_fabricated_citations_are_dropped():
    resolved, dropped, _ = _resolve("src/made_up.py:L1-L4", "commit 1", "ENG-999")
    assert resolved == []
    assert len(dropped) == 3


def test_model_output_keeps_only_the_first_fifteen_citations():
    output = ModelOutput.model_validate({
        "justification": "A justification of sufficient length.",
        "score": 6,
        "evidence_citations": [
            {"identifier": f"src/app.py:L{n}", "reason": "a reason that is long enough"}
            for n in range(1, 21)
        ],
    })
    assert len(output.evidence_citations) == 15


@pytest.mark.parametrize("model", ["sprintsight-qwen", "sprintsight-qwen25-32b"])
def test_full_prompt_fits_the_model_context(model):
    bundle = ArtifactBundle.model_validate(_bundle(600))
    context = min(llm_client.MODEL_NUM_CTX[model], llm_client._CONTEXT_CAP)
    for dimension in DIMENSIONS:
        built = llm_client.build_dimension_prompt(bundle, dimension, DIMENSION_PROMPTS[dimension], model)
        assert built.stats["mode"] == "packed"
        total = estimate_tokens(built.prompt) + llm_client._SCHEMA_OVERHEAD_TOKENS
        assert total + llm_client._OUTPUT_RESERVE_TOKENS <= context


def test_legacy_mode_still_samples_thirty_commits(monkeypatch):
    monkeypatch.setattr(llm_client, "_EVIDENCE_MODE", "legacy")
    bundle = ArtifactBundle.model_validate(_bundle(100))
    built = llm_client.build_dimension_prompt(bundle, "code_quality", DIMENSION_PROMPTS["code_quality"], "sprintsight-qwen")
    assert built.index is None
    assert built.stats == {"mode": "legacy", "commits_listed": 30}


class _FakeCompletions:
    def __init__(self, output: ModelOutput):
        self.output = output
        self.prompts: list[str] = []

    async def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"])
        return self.output


class _FakeClient:
    def __init__(self, output: ModelOutput):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(output)})()


def test_evaluate_dimension_returns_resolved_file_line_citations(monkeypatch, tmp_path):
    import asyncio

    from services import audit_logger

    monkeypatch.setenv("MLFLOW_TRACKING_URI", tmp_path.as_uri())
    monkeypatch.setattr(audit_logger, "AUDIT_LOG_DIR", tmp_path)
    bob_sha = _bundle()["commits"][1]["sha"]
    output = ModelOutput.model_validate({
        "justification": "Readable service class with a focused change history.",
        "score": 7,
        "evidence_citations": [
            {"identifier": "src/app.py:L3-L5", "reason": "Service class is small and single-purpose."},
            {"identifier": f"src/app.py:L4-L5@{bob_sha[:7]}", "reason": "Refactor names the computed value."},
            {"identifier": "src/ghost.py:L1-L9", "reason": "This file does not exist in the repo."},
        ],
    })
    client = _FakeClient(output)
    monkeypatch.setattr(llm_client, "create_llm_client", lambda: client)

    result = asyncio.run(llm_client.evaluate_dimension(
        ArtifactBundle.model_validate(_bundle()), "code_quality", "sprintsight-qwen",
        DIMENSION_PROMPTS["code_quality"], num_ctx=49152,
    ))

    assert "=== FILE src/app.py" in client.chat.completions.prompts[0]
    assert [(c.kind, c.identifier, c.line_start, c.line_end) for c in result.evidence_citations] == [
        ("file_lines", "src/app.py:L3-L5", 3, 5),
        ("diff_lines", f"src/app.py:L4-L5@{bob_sha[:7]}", 4, 5),
    ]
    assert result.evidence_citations[1].commit_sha == bob_sha
    assert any("ungrounded_citations_dropped" in p.read_text(encoding="utf-8") for p in tmp_path.glob("*.txt"))


@pytest.mark.parametrize("model", ["sprintsight-mistral", "sprintsight-qwen25-32b"])
def test_full_prompt_fits_the_real_context_of_dense_tokenizers(model):
    # The packer counts chars / 3.0; mistral's tokenizer makes ~21% more real
    # tokens than that, which overflowed its 32K context before.
    bundle = ArtifactBundle.model_validate(_bundle(600))
    for dimension in DIMENSIONS:
        built = llm_client.build_dimension_prompt(bundle, dimension, DIMENSION_PROMPTS[dimension], model)
        estimated = estimate_tokens(built.prompt) + llm_client._SCHEMA_OVERHEAD_TOKENS
        real = estimated * llm_client.CHARS_PER_TOKEN / llm_client.MODEL_CHARS_PER_TOKEN[model]
        assert real + llm_client._OUTPUT_RESERVE_TOKENS <= llm_client.MODEL_NUM_CTX[model]
