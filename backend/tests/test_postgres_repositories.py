"""Postgres SQL that earlier fixes changed and the in-memory repositories cannot exercise
(skipped when TEST_DATABASE_URL is not set): the token version bump on an email change and the
manual report PATCH against the table's CHECK constraint."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.security import hash_password
from app.repositories.interfaces import ProjectRecord, UserRecord
from app.repositories.postgres import (
    PostgresAssessmentRepository,
    PostgresProjectRepository,
    PostgresUserRepository,
)
from app.schemas.assessment import (
    AssessmentReport,
    ManualAssessmentPatch,
    RubricDimensionScoreDetail,
    TeamScore,
)
from app.schemas.auth import Role
from app.services.assessmentService.service import update_manual_assessment

WEIGHTS = {
    "requirements": 0.2,
    "code_quality": 0.2,
    "testing": 0.2,
    "documentation": 0.1,
    "collaboration": 0.1,
    "cicd": 0.2,
}


@pytest.fixture
def pool(postgres_pool):
    with postgres_pool.connection() as connection:
        connection.execute("TRUNCATE users CASCADE")
    return postgres_pool


def make_user(email: str = "student@example.com", role: Role = Role.STUDENT) -> UserRecord:
    return UserRecord(
        id=str(uuid4()),
        email=email,
        full_name="Test User",
        role=role,
        hashed_password=hash_password("password123"),
    )


def test_changing_an_email_invalidates_sessions_but_other_edits_do_not(pool) -> None:
    users = PostgresUserRepository(pool)
    user = users.create_user(make_user("old@example.com"))
    assert user.token_version == 0

    renamed = users.update_user(user.id, "old@example.com", "New Name", Role.STUDENT, True)
    recased = users.update_user(user.id, "OLD@example.com", "New Name", Role.STUDENT, True)
    moved = users.update_user(user.id, "new@example.com", "New Name", Role.STUDENT, True)

    assert renamed is not None and renamed.token_version == 0
    assert recased is not None and recased.token_version == 0  # same address, other case
    assert moved is not None and moved.token_version == 1
    assert moved.email == "new@example.com"


@pytest.fixture
def report_setup(pool):
    users = PostgresUserRepository(pool)
    projects = PostgresProjectRepository(pool)
    reports = PostgresAssessmentRepository(pool)
    instructor = users.create_user(make_user("teacher@example.com", Role.INSTRUCTOR))
    course = projects.create_course("CS480", "Capstone", "001", 2026, "Fall", instructor.id)
    projects.assign_instructor(course.id, instructor.id)
    project = projects.create_project(
        ProjectRecord(
            id=str(uuid4()),
            project_name="P",
            team_name="T",
            description=None,
            course_id=course.id,
            course_code="CS480",
            github_repo_url=None,
            local_repo_path=None,
            created_by=instructor.id,
            created_at=datetime.now(UTC),
        ),
        [],
    )
    return reports, projects, instructor, course, project


def failed_report(course_id: str, project_id: str, failed: str = "testing") -> AssessmentReport:
    """An AI report where one dimension could not be scored (placeholder score 1)."""
    scores = {
        "requirements": 8,
        "code_quality": 7,
        "testing": 6,
        "documentation": 9,
        "collaboration": 5,
        "cicd": 4,
        failed: 1,
    }
    details = {
        name: RubricDimensionScoreDetail(score=value, justification=f"AI on {name}")
        for name, value in scores.items()
    }
    details[failed].evaluation_failed = True
    details[failed].failure_class = "timeout"
    return AssessmentReport(
        report_id=f"rpt-{uuid4()}",
        model_name="m",
        mode="test",
        course_id=course_id,
        project_id=project_id,
        sprint_id="sprint-1",
        generated_at=datetime.now(UTC),
        rubric_weights=WEIGHTS,
        team_score=TeamScore(
            score=72.5,
            rationale=(
                f"Incomplete assessment: {failed} could not be scored automatically and is "
                "excluded from this score pending manual review. AI summary"
            ),
        ),
        individual_scores=[],
        recommendations=[],
        rubric_scores=details,
        evaluation_failed=True,
        failed_dimensions=[failed],
    )


def patch_body(failed: str = "testing", **overrides) -> ManualAssessmentPatch:
    """What the editor sends after loading the report and saving without touching the failed
    dimension: every legacy field as displayed (0-100), the stored text and the placeholder."""
    scores = {"requirements": 80, "code_quality": 70, "documentation": 90, "collaboration": 50}
    if failed in scores:
        scores[failed] = 10  # the placeholder 1, shown as 10/100
    body = {
        **{f"{name}_score": value for name, value in scores.items()},
        **{f"{name}_justification": f"AI on {name}" for name in scores},
        **overrides,
    }
    return ManualAssessmentPatch.model_validate(body)


@pytest.mark.parametrize("failed", ["testing", "code_quality"])
def test_a_manual_edit_that_leaves_a_dimension_failed_satisfies_the_override_constraint(
    report_setup, failed: str
) -> None:
    """The table requires all four legacy scores once override is set. That includes a failed
    legacy dimension (code_quality), which must not be written as NULL."""
    reports, projects, instructor, course, project = report_setup
    stored = failed_report(course.id, project.id, failed)
    reports.save_report(stored)

    updated = update_manual_assessment(
        stored.report_id, patch_body(failed), instructor.id, reports, projects
    )

    assert updated.override is True
    assert updated.evaluation_failed is True and updated.failed_dimensions == [failed]
    assert updated.requirements_score == 80 and updated.collaboration_score == 50
    assert updated.code_quality_score is not None
    reloaded = reports.get_report(stored.report_id)
    assert reloaded is not None and reloaded.failed_dimensions == [failed]


def test_scoring_the_failed_dimension_persists_the_cleared_flags_and_the_new_grade(
    report_setup,
) -> None:
    reports, projects, instructor, course, project = report_setup
    stored = failed_report(course.id, project.id)
    reports.save_report(stored)
    body = patch_body(
        rubric_scores={"testing": {"score": 9, "justification": "Instructor scored the tests."}}
    )

    update_manual_assessment(stored.report_id, body, instructor.id, reports, projects)

    reloaded = reports.get_report(stored.report_id)
    assert reloaded is not None
    assert reloaded.evaluation_failed is False and reloaded.failed_dimensions == []
    assert reloaded.rubric_scores["testing"].evaluation_failed is False
    assert all(0 <= detail.score <= 10 for detail in reloaded.rubric_scores.values())
    # 8*.2 + 7*.2 + 9*.2 + 9*.1 + 5*.1 + 4*.2 = 7.0
    assert reloaded.team_score.score == pytest.approx(70.0)
    assert reloaded.team_score.rationale == "AI summary"
    assert reloaded.team_score.overall_grade


def test_a_report_is_found_by_its_rpt_prefixed_id_and_a_malformed_id_is_just_missing(
    report_setup,
) -> None:
    """Reports are addressed as "rpt-<uuid>"; the lookup used to raise (a 500) on that form."""
    reports, _, _, course, project = report_setup
    stored = failed_report(course.id, project.id)
    reports.save_report(stored)

    by_prefixed_id = reports.get_report(stored.report_id)
    by_bare_uuid = reports.get_report(stored.report_id.removeprefix("rpt-"))

    assert by_prefixed_id is not None and by_prefixed_id.course_id == course.id
    assert by_bare_uuid is not None and by_bare_uuid.course_id == course.id
    assert reports.get_report("rpt-not-a-uuid") is None
    assert reports.get_report(f"rpt-{uuid4()}") is None

