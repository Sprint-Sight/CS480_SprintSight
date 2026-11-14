"""Seed blind labels from a reference instructor so agreement has data.

Dry run by default. Labels go through the same table/worker as real ones, so they sync
to MLflow as HUMAN assessments. Never marks scores as seen, so labels stay blind.

  docker exec sprintsight-backend python -m scripts.seed_insights_demo \
      --instructor instr.b@demo --limit 6
  docker exec sprintsight-backend python -m scripts.seed_insights_demo \
      --instructor instr.b@demo --limit 6 --apply
"""

import argparse
import random

from app.core.config import get_settings
from app.repositories.insights import DIMENSIONS, LabelInput, PostgresInsightsRepository
from app.repositories.postgres import (
    PostgresAssessmentRepository,
    PostgresProjectRepository,
    PostgresUserRepository,
    create_user_pool,
)
from app.services.insightsService.service import original_ai_scores

OFFSETS = [-2, -1, -1, 0, 0, 0, 0, 1, 1, 2]  # realistic human-vs-AI gaps


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instructor", required=True, help="email of the reference instructor")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    pool = create_user_pool(get_settings().database_connection_string())
    pool.open(wait=True)
    users, projects = PostgresUserRepository(pool), PostgresProjectRepository(pool)
    reports, insights = PostgresAssessmentRepository(pool), PostgresInsightsRepository(pool)
    instructor = users.get_by_email(args.instructor)
    if instructor is None:
        raise SystemExit(f"No user {args.instructor}")

    course_ids = projects.list_instructor_course_ids(instructor.id)
    runs = [run for run in insights.list_runs(course_ids) if run.trace_id]
    print(f"{len(runs)} trace-linked reports in {args.instructor}'s courses")
    for run in runs:
        print(
            f"  {run.report_id}  {run.course_code} {run.section}  {run.team_name:<20} "
            f"{run.sprint_id:<12} {run.model_name:<22} judge={run.judge_status}"
        )

    seeded = 0
    for run in runs:
        if seeded >= args.limit:
            break
        if insights.labels_for(run.report_id, instructor.id):
            continue
        original = original_ai_scores(reports.get_report(run.report_id)) or {}
        rng = random.Random(run.report_id)  # deterministic demo data per report, not security
        items = [
            LabelInput(
                dimension,
                max(1, min(10, round(original.get(dimension, 6)) + rng.choice(OFFSETS))),
                "Seeded reference label",
            )
            for dimension in DIMENSIONS
        ]
        print(
            f"{'SEED' if args.apply else 'would seed'} {run.team_name} {run.model_name}: "
            + ", ".join(f"{item.dimension}={item.score}" for item in items)
        )
        if args.apply:
            insights.stamp_view(run.report_id, instructor.id, score_seen=False)
            insights.upsert_labels(
                run.report_id,
                instructor.id,
                items,
                is_blind=True,
                snapshots={dimension: original.get(dimension) for dimension in DIMENSIONS},
            )
        seeded += 1
    print("Done." if args.apply else "Dry run only; add --apply to write.")
    pool.close()


if __name__ == "__main__":
    main()
