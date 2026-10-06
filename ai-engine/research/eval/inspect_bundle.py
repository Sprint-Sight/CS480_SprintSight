"""Show exactly what gets sent to the LLM for a given ArtifactBundle, without
actually calling the model.

This answers the three recurring questions:

  1. "What does the LLM see per dimension?" — prints the full bundle_data
     JSON that `render_dimension_prompt` embeds under 'Student Artifacts',
     after `_trim_commits` and `_select_representative_commits` have run.

  2. "Are my commits being sampled, and if so which ones?" — prints before
     and after counts, and lists the SHAs that survived the budget cut.

  3. "Are Jira tickets actually flowing through?" — prints the ticket
     count, their status/type/assignee breakdown, and names the dimensions
     where they ARE and are NOT shown to the model.

Usage:

    python -m research.eval.inspect_bundle \\
        --dataset d_real_sprints \\
        --example fencing_sp1 \\
        --dimensions code_quality,requirements,collaboration \\
        --out research/eval_inspection

Writes one `<example>__<dim>.prompt.txt` per dimension (the exact text that
would be sent to the model, bundle_data block included) plus a
`<example>__summary.json` with the sampling/presence stats.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any
from pathlib import Path

from prompts.dimension_criteria import DIMENSION_PROMPTS, DIMENSIONS
from prompts.templates import render_dimension_prompt
from research.eval.datasets import load_dataset
from services import llm_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("research.eval.inspect")


def _ticket_breakdown(tickets: list[dict]) -> dict:
    """Mirror what _compute_jira_facts tells the model, in a terse dict."""
    from collections import Counter
    status = Counter(t.get("status") or "Unknown" for t in tickets)
    type_c = Counter(t.get("issue_type") or "Unknown" for t in tickets)
    assignee = Counter(t.get("assignee") or "Unassigned" for t in tickets)
    sp_total = sum((t.get("story_points") or 0) for t in tickets)
    sp_done = sum((t.get("story_points") or 0) for t in tickets if t.get("status") == "Done")
    return {
        "count": len(tickets),
        "by_status": dict(status),
        "by_type": dict(type_c),
        "by_assignee": dict(assignee),
        "story_points_total": sp_total,
        "story_points_done": sp_done,
    }


def inspect(dataset_name: str, example_id: str, dimensions: list[str], out_dir: Path) -> dict:
    items, ds_hash, _ = load_dataset(dataset_name, subset=[example_id])
    if not items:
        raise LookupError(f"example '{example_id}' not in dataset '{dataset_name}'")
    item = items[0]
    bundle = item.bundle
    full = bundle.model_dump(mode="json")

    # Access the private helpers directly — they ARE what the production
    # path uses, so inspecting them is inspecting what the model sees.
    trimmed_commits = llm_client._trim_commits(full["commits"])
    budget = llm_client._COMMIT_BUDGET

    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "dataset": dataset_name,
        "dataset_hash": ds_hash,
        "example_id": example_id,
        "team_id": bundle.team_id,
        "sprint_id": bundle.sprint_id,
        "raw_commit_count": len(full["commits"]),
        "trimmed_commit_count": len(trimmed_commits),
        "commit_budget_per_dimension": budget,
        "jira_tickets": _ticket_breakdown(full["jira_tickets"]),
        "peer_evaluations_count": len(full["peer_evaluations"]),
        "collaboration_metrics_keys": sorted(full.get("collaboration_metrics", {}).keys()),
        "artifact_metrics_keys": sorted(full.get("artifact_metrics", {}).keys()),
        "project_context_documents_count": len(full.get("project_context_documents", [])),
        "instructor_expectations_chars": len(bundle.instructor_expectations or ""),
        "per_dimension": {},
    }

    for dim in dimensions:
        if dim not in DIMENSIONS:
            log.warning("Skipping unknown dimension: %s", dim)
            continue
        fields = llm_client._DIMENSION_ARTIFACT_FIELDS[dim]
        sampled = None
        if "commits" in fields:
            sampled = llm_client._select_representative_commits(trimmed_commits, dim, budget)
        bundle_data = llm_client._dimension_bundle_data(bundle, dim, sampled)
        commit_facts = llm_client._compute_commit_facts(trimmed_commits, budget) if "commits" in fields else ""
        jira_facts = llm_client._compute_jira_facts(full["jira_tickets"]) if "jira_tickets" in fields else ""
        computed_facts = "\n\n    ".join(filter(None, [commit_facts, jira_facts]))
        project_context = llm_client._format_project_context_documents(bundle)
        prompt = render_dimension_prompt(
            dim, DIMENSION_PROMPTS[dim], bundle_data, computed_facts, project_context,
        )

        prompt_path = out_dir / f"{example_id}__{dim}.prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        bundle_data_path = out_dir / f"{example_id}__{dim}.bundle_data.json"
        bundle_data_path.write_text(bundle_data, encoding="utf-8")

        summary["per_dimension"][dim] = {
            "fields_included": list(fields),
            "has_commits": "commits" in fields,
            "has_jira_tickets": "jira_tickets" in fields,
            "has_peer_evaluations": "peer_evaluations" in fields,
            "has_artifact_metrics": "artifact_metrics" in fields,
            "has_collaboration_metrics": "collaboration_metrics" in fields,
            "commits_sent_to_model": len(sampled) if sampled is not None else 0,
            "commits_sampled_shas": [c.get("sha") for c in (sampled or [])],
            "prompt_chars": len(prompt),
            "prompt_approx_tokens": len(prompt) // 4,
            "prompt_file": str(prompt_path),
            "bundle_data_file": str(bundle_data_path),
        }

        if "jira_tickets" in fields and len(full["jira_tickets"]) == 0:
            summary["per_dimension"][dim]["jira_warning"] = (
                "Dimension uses jira_tickets but the bundle has 0 tickets — "
                "the model will correctly report 'no data'. Confirm ingestion "
                "via GET /api/v1/jira-ingestion/raw/<project_id> or check "
                "jira_ingestion_runs in Postgres."
            )

    summary_path = out_dir / f"{example_id}__summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Wrote inspection summary to %s", summary_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="d_real_sprints")
    parser.add_argument("--example", required=True, help="Dataset example_id (JSON filename stem).")
    parser.add_argument("--dimensions", default=",".join(DIMENSIONS),
                        help="Comma-separated dimensions to inspect (default: all 6).")
    parser.add_argument("--out", type=Path, default=Path("research/eval_inspection"))
    args = parser.parse_args(argv)
    dims = [d.strip() for d in args.dimensions.split(",") if d.strip()]
    summary = inspect(args.dataset, args.example, dims, args.out)

    # Terminal summary — the headline numbers you asked about.
    print("\n== Inspection summary ==")
    print(f"Example: {summary['example_id']} (team={summary['team_id']} sprint={summary['sprint_id']})")
    print(f"Dataset: {summary['dataset']} @ {summary['dataset_hash']}")
    print(f"Commits: raw={summary['raw_commit_count']}  trimmed={summary['trimmed_commit_count']}  budget_per_dim={summary['commit_budget_per_dimension']}")
    print(f"Jira:    tickets={summary['jira_tickets']['count']}  by_status={summary['jira_tickets']['by_status']}")
    print(f"Peer evals: {summary['peer_evaluations_count']}")
    print(f"Context docs: {summary['project_context_documents_count']}")
    print()
    print("Per-dimension (what the model receives):")
    for dim, info in summary["per_dimension"].items():
        marks = []
        marks.append(f"commits={info['commits_sent_to_model']}" if info["has_commits"] else "commits=—")
        marks.append("jira=Y" if info["has_jira_tickets"] else "jira=—")
        marks.append("peer=Y" if info["has_peer_evaluations"] else "peer=—")
        marks.append(f"~{info['prompt_approx_tokens']}tok")
        warn = f"  {info['jira_warning']}" if "jira_warning" in info else ""
        print(f"  {dim:<16} {'  '.join(marks)}{warn}")
    print(f"\nFull prompts written under: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
