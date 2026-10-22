"""Export ingested sprints from Postgres as ArtifactBundle JSON files.

The AI engine's model-comparison pipeline (ai-engine/research/eval/) reads
one JSON file per sprint from a directory, so this script's job is to
turn a list of (course_id, project_id, sprint_id) triples into exactly
that: one ArtifactBundle-shaped JSON per sprint, named by filename.

Example — export the two sprints you've already ingested:

    python -m scripts.export_eval_bundles \\
        --triple cs203,proj-a,sprint-1,proj_a_s1 \\
        --triple cs203,proj-b,sprint-1,proj_b_s1 \\
        --out ../ai-engine/research/eval/data/real_sprints

Each --triple is `course_id,project_id,sprint_id,output_name`. The
`output_name` becomes the JSON filename (and therefore the example_id in
every subsequent MLflow run and plot). Pick stable names — a rename later
produces a different dataset hash.

Data pulled from Postgres (via the same repositories the API uses):

    metrics        <- PostgresMetricsRepository.get_metrics
    jira_tickets   <- PostgresJiraIngestionRunRepository.list_runs (latest
                      cleaned_snapshot)
    manual_text    <- PostgresManualTextRepository.get
    documents      <- optional; off by default because it needs MinIO.
                      Pass --with-documents and set MINIO_* env vars to
                      include extracted document text.

Everything else that an ArtifactBundle expects but doesn't come from
Postgres (artifact_metrics) is written as empty — the production pipeline
treats those as optional too.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _import_backend_bits():
    """Imported lazily so --help works without the backend env configured."""
    # Settings/env must be ready before touching Postgres.
    from app.core.config import get_settings
    from app.repositories.postgres import (
        PostgresDocumentRepository,
        PostgresJiraIngestionRunRepository,
        PostgresManualTextRepository,
        PostgresMetricsRepository,
        create_user_pool,
    )
    from app.services.documentsService.service import collect_project_context_documents
    return (
        get_settings,
        create_user_pool,
        PostgresMetricsRepository,
        PostgresJiraIngestionRunRepository,
        PostgresManualTextRepository,
        PostgresDocumentRepository,
        collect_project_context_documents,
    )


def _collaboration_metrics_from_metrics(metrics) -> dict[str, Any]:
    """Mirror the shape the AI engine's BackendCollaborationMetrics expects
    (see ai-engine/api/assessment.py). Keeping it structural so a future
    field drift is caught by Pydantic parsing on the AI-engine side rather
    than by a mysterious KeyError here."""
    return {
        "commit_frequency": metrics.commit_frequency,
        "code_churn": metrics.code_churn,
        "pr_turnaround_hours": metrics.pr_turnaround_hours,
        "assigned_story_points": metrics.assigned_story_points,
        "completion_percent": metrics.completion_percent,
    }


def _latest_jira_tickets(jira_repo, project_id: str, sprint_id: str) -> list[dict]:
    runs = jira_repo.list_runs(project_id, sprint_id)
    processed = [r for r in runs if r.cleaned_snapshot]
    if not processed:
        return []
    latest = max(processed, key=lambda r: r.captured_at)
    return [ticket.model_dump(mode="json") for ticket in latest.cleaned_snapshot.tickets]


def _bundle_dict_from_db(
    course_id: str,
    project_id: str,
    sprint_id: str,
    metrics_repo,
    jira_repo,
    manual_repo,
    document_repo=None,
    storage=None,
    include_documents: bool = False,
) -> dict[str, Any]:
    """Build an ArtifactBundle-shaped dict for ONE sprint. Shape matches
    ai-engine/schemas/artifact_bundle.ArtifactBundle so the dataset loader
    can parse it with `ArtifactBundle.model_validate(...)`.
    """
    metrics = metrics_repo.get_metrics(course_id, project_id, sprint_id)
    if metrics is None:
        raise LookupError(
            f"No metrics in Postgres for (course_id={course_id}, "
            f"project_id={project_id}, sprint_id={sprint_id}). Ingest the "
            f"repo first via /api/v1/ingestion/sync, then rerun this export."
        )
    jira_tickets = _latest_jira_tickets(jira_repo, project_id, sprint_id)
    manual_text = manual_repo.get(course_id, project_id, sprint_id) or "No instructor guidance provided."

    project_context_documents: list[dict] = []
    if include_documents and document_repo is not None and storage is not None:
        try:
            # Re-use the production path so the export is faithful to what
            # the AI engine actually sees in a live /assess call.
            from app.services.documentsService.service import collect_project_context_documents
            project_context_documents = collect_project_context_documents(project_id, document_repo, storage)
        except Exception:
            log.exception("Document collection failed; writing bundle without context docs.")

    return {
        # Fields in ArtifactBundle (ai-engine/schemas/artifact_bundle.py)
        "team_id": project_id,
        "sprint_id": sprint_id,
        "commits": [commit.model_dump(mode="json") for commit in metrics.commits],
        "jira_tickets": jira_tickets,
        "collaboration_metrics": _collaboration_metrics_from_metrics(metrics),
        "artifact_metrics": {},  # Reserved; mock was removed in the docs work
        "project_context_documents": project_context_documents,
        "instructor_expectations": manual_text,
    }


def _parse_triple(raw: str) -> tuple[str, str, str, str]:
    parts = raw.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            f"--triple must be course_id,project_id,sprint_id,output_name (got {raw!r})"
        )
    course_id, project_id, sprint_id, output_name = (p.strip() for p in parts)
    if not all([course_id, project_id, sprint_id, output_name]):
        raise argparse.ArgumentTypeError(f"--triple has empty fields: {raw!r}")
    return course_id, project_id, sprint_id, output_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--triple", action="append", type=_parse_triple, required=True, metavar="C,P,S,NAME",
        help="course_id,project_id,sprint_id,output_name. Repeat for multiple sprints.",
    )
    parser.add_argument(
        "--out", type=Path, required=True,
        help="Output directory (e.g. ../ai-engine/research/eval/data/real_sprints).",
    )
    parser.add_argument(
        "--with-documents", action="store_true",
        help="Include extracted project_context_documents. Requires MinIO env vars.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing JSON files; default is to skip them.",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    log.info("Writing bundles to %s", args.out.resolve())

    (
        get_settings,
        create_user_pool,
        MetricsRepo,
        JiraRepo,
        ManualTextRepo,
        DocumentRepo,
        _collect,
    ) = _import_backend_bits()

    settings = get_settings()
    pool = create_user_pool(settings.database_connection_string())
    pool.open(wait=True)
    try:
        metrics_repo = MetricsRepo(pool)
        jira_repo = JiraRepo(pool)
        manual_repo = ManualTextRepo(pool)

        storage = None
        document_repo = None
        if args.with_documents:
            # Imported here so a bundle export without --with-documents
            # doesn't require boto3/MinIO to be reachable.
            from app.core.storage import storage as default_storage
            document_repo = DocumentRepo(pool)
            storage = default_storage

        exit_code = 0
        for course_id, project_id, sprint_id, output_name in args.triple:
            dest = args.out / f"{output_name}.json"
            if dest.exists() and not args.overwrite:
                log.info("Skipping existing %s (pass --overwrite to replace).", dest.name)
                continue
            try:
                bundle = _bundle_dict_from_db(
                    course_id, project_id, sprint_id,
                    metrics_repo, jira_repo, manual_repo,
                    document_repo=document_repo, storage=storage,
                    include_documents=args.with_documents,
                )
            except LookupError as exc:
                log.error("Skipping %s: %s", output_name, exc)
                exit_code = 1
                continue
            with dest.open("w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2, ensure_ascii=True)
            log.info(
                "Wrote %s (commits=%d, tickets=%d, docs=%d).",
                dest.name,
                len(bundle["commits"]),
                len(bundle["jira_tickets"]),
                len(bundle["project_context_documents"]),
            )
        return exit_code
    finally:
        pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
