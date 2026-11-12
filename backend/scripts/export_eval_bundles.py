"""Export sprints as the exact ArtifactBundle the AI engine grades in a live assessment.

The AI engine's model-comparison pipeline (ai-engine/evaluation/offline/) reads one JSON file per
sprint from a directory (the `d_real_sprints` dataset). Each file here is built the way
`run_assessment_job` builds a live request: commits re-extracted from the project's local
repository (`ingest_github_metrics`, which also saves them, as an assessment does), the latest
processed Jira snapshot without changelogs, instructor expectations, uploaded context documents
and the repository snapshot at HEAD, assembled by `build_assessment_payload`. The payload is then
mapped to an ArtifactBundle the way ai-engine/api/assessment.py maps it, so the offline dataset
is what production would grade.

Run it inside the backend container (it needs the database, MinIO and the mounted repositories;
`scripts/` is not part of the image, so copy it in), from the repository root:

    docker cp backend/scripts/export_eval_bundles.py sprintsight-backend:/tmp/export_eval_bundles.py
    docker exec -e PYTHONPATH=/app -w /app sprintsight-backend \\
        python /tmp/export_eval_bundles.py --course CS203 --out /tmp/real_sprints
    docker cp sprintsight-backend:/tmp/real_sprints/. \\
        ai-engine/evaluation/benchmarks/data/real_sprints/

Selecting sprints:

    --course CS203                 every project of the course x every sprint that has a Jira
                                   ingestion run; each file is named <team>_<sprint>, e.g.
                                   ftms_sprint-1.json
    --triple C,P,S,NAME            one sprint by course_id, project_id, sprint_id and file name;
                                   repeatable

The file name becomes the example_id in every MLflow run and plot, and the dataset hash covers
the file contents, so a rename or a re-export with new data is a different dataset.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# The fields ai-engine/api/assessment.py copies from the payload into its ArtifactBundle.
BUNDLE_FIELDS = (
    "team_id",
    "sprint_id",
    "commits",
    "jira_tickets",
    "peer_evaluations",
    "collaboration_metrics",
    "artifact_metrics",
    "project_context_documents",
    "repo_snapshot",
    "instructor_expectations",
)


@dataclass(frozen=True)
class SprintRef:
    course_id: str
    project_id: str
    sprint_id: str
    output_name: str


def bundle_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The ArtifactBundle the AI engine builds from a live payload (ai-engine/api/assessment.py):
    the project id is the team id, and absent optional lists default to empty."""
    context = payload["sprint_context"]
    return {
        "team_id": context["project_id"],
        "sprint_id": context["sprint_id"],
        "commits": payload.get("commits") or [],
        "jira_tickets": payload.get("jira_tickets") or [],
        "peer_evaluations": payload.get("peer_evaluations") or [],
        "collaboration_metrics": payload.get("collaboration_metrics") or {},
        "artifact_metrics": payload.get("artifact_metrics") or {},
        "project_context_documents": payload.get("project_context_documents") or [],
        "repo_snapshot": payload.get("repo_snapshot"),
        "instructor_expectations": payload.get(
            "instructor_expectations", "No instructor guidance provided."
        ),
    }


def latest_jira_tickets(jira_repo, project_id: str, sprint_id: str) -> list[dict]:
    """The latest processed Jira snapshot, serialised as run_assessment_job serialises it."""
    processed = [run for run in jira_repo.list_runs(project_id, sprint_id) if run.cleaned_snapshot]
    if not processed:
        return []
    latest = max(processed, key=lambda run: run.captured_at)
    return [
        ticket.model_dump(mode="json", exclude={"changelog"})
        for ticket in latest.cleaned_snapshot.tickets
    ]


def build_live_payload(ref: SprintRef, project, repos: dict[str, Any], storage) -> dict[str, Any]:
    """Collect one sprint's inputs exactly as run_assessment_job does, then build the payload."""
    from app.schemas.assessment import AssessRequest
    from app.services.documentsService.service import collect_project_context_documents
    from app.services.gitlabGithub.service import (
        collect_repository_snapshot,
        ingest_github_metrics,
        resolve_local_repository_path,
    )
    from app.services.manualTextService.service import get_manual_text
    from app.services.middleManService.service import build_assessment_payload

    if not project.local_repo_path:
        raise LookupError(f"project {project.team_name!r} has no local repository configured")
    try:
        repository_path = resolve_local_repository_path(project.local_repo_path)
    except ValueError as exc:
        raise LookupError(f"project {project.team_name!r}: {exc}") from exc

    request = AssessRequest(
        course_id=ref.course_id, project_id=ref.project_id, sprint_id=ref.sprint_id
    )
    metrics = ingest_github_metrics(request, repository_path, repos["metrics"])
    manual_text = get_manual_text(repos["manual"], ref.course_id, ref.project_id, ref.sprint_id)
    jira_tickets = latest_jira_tickets(repos["jira"], ref.project_id, ref.sprint_id)

    project_context_documents: list[dict] = []
    try:
        project_context_documents = collect_project_context_documents(
            ref.project_id, repos["documents"], storage
        )
    except Exception:
        log.exception(
            "Document collection failed for %s; continuing without them.", ref.output_name
        )

    repo_snapshot: dict | None = None
    try:
        repo_snapshot = collect_repository_snapshot(repository_path, metrics.head_sha or "HEAD")
    except Exception:
        log.exception(
            "Repository snapshot failed for %s; continuing with history only.", ref.output_name
        )

    return build_assessment_payload(
        metrics, {}, manual_text, jira_tickets, project_context_documents, repo_snapshot
    )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "_", text.strip().lower()).strip("_")


def sprints_for_course(course_code_or_id: str, project_repo, jira_repo) -> list[SprintRef]:
    """Every project of the course x every sprint that has a Jira ingestion run."""
    wanted = course_code_or_id.strip().lower()
    courses = [
        c for c in project_repo.list_courses() if wanted in (c.id.lower(), c.code.strip().lower())
    ]
    if not courses:
        raise LookupError(f"no course with code or id {course_code_or_id!r}")
    if len(courses) > 1:
        options = ", ".join(f"{c.id} ({c.code} {c.section} {c.year} {c.term})" for c in courses)
        raise LookupError(f"course code {course_code_or_id!r} is ambiguous; pass an id: {options}")
    course = courses[0]
    refs: list[SprintRef] = []
    for project in sorted(project_repo.list_projects(course.id), key=lambda p: p.team_name.lower()):
        sprint_ids = sorted({run.sprint_id for run in jira_repo.list_project_runs(project.id)})
        if not sprint_ids:
            log.warning(
                "Project %r has no Jira ingestion runs; nothing to export.", project.team_name
            )
        for sprint_id in sprint_ids:
            name = f"{slug(project.team_name)}_{slug(sprint_id)}"
            refs.append(SprintRef(course.id, project.id, sprint_id, name))
    names = [ref.output_name for ref in refs]
    if len(set(names)) != len(names):
        raise LookupError(f"two sprints map to the same file name: {sorted(names)}")
    return refs


def parse_triple(raw: str) -> SprintRef:
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4 or not all(parts):
        raise argparse.ArgumentTypeError(
            f"--triple must be course_id,project_id,sprint_id,output_name (got {raw!r})"
        )
    return SprintRef(*parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--course", help="Course code or id: export every project and sprint.")
    selection.add_argument(
        "--triple",
        action="append",
        type=parse_triple,
        metavar="C,P,S,NAME",
        help="course_id,project_id,sprint_id,output_name. Repeat for several sprints.",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing files (default: skip them)."
    )
    args = parser.parse_args(argv)

    from app.core.config import get_settings
    from app.core.storage import storage
    from app.repositories.postgres import (
        PostgresDocumentRepository,
        PostgresJiraIngestionRunRepository,
        PostgresManualTextRepository,
        PostgresMetricsRepository,
        PostgresProjectRepository,
        create_user_pool,
    )

    pool = create_user_pool(get_settings().database_connection_string())
    pool.open(wait=True)
    try:
        repos = {
            "metrics": PostgresMetricsRepository(pool),
            "jira": PostgresJiraIngestionRunRepository(pool),
            "manual": PostgresManualTextRepository(pool),
            "documents": PostgresDocumentRepository(pool),
            "projects": PostgresProjectRepository(pool),
        }
        refs = args.triple or sprints_for_course(args.course, repos["projects"], repos["jira"])
        return export(refs, repos, storage, args.out, overwrite=args.overwrite)
    finally:
        pool.close()


def export(
    refs: list[SprintRef], repos: dict[str, Any], storage, out: Path, *, overwrite: bool
) -> int:
    out.mkdir(parents=True, exist_ok=True)
    log.info("Writing %d bundle(s) to %s", len(refs), out.resolve())
    exit_code = 0
    for ref in refs:
        dest = out / f"{ref.output_name}.json"
        if dest.exists() and not overwrite:
            log.info("Skipping existing %s (pass --overwrite to replace).", dest.name)
            continue
        project = repos["projects"].get_project(ref.project_id)
        try:
            if project is None:
                raise LookupError(f"no project {ref.project_id}")
            bundle = bundle_from_payload(build_live_payload(ref, project, repos, storage))
        except LookupError as exc:
            log.error("Skipping %s: %s", ref.output_name, exc)
            exit_code = 1
            continue
        with dest.open("w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=True)
        snapshot = bundle["repo_snapshot"] or {}
        log.info(
            "Wrote %s (commits=%d, tickets=%d, docs=%d, snapshot files=%d).",
            dest.name,
            len(bundle["commits"]),
            len(bundle["jira_tickets"]),
            len(bundle["project_context_documents"]),
            len(snapshot.get("files") or []),
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
