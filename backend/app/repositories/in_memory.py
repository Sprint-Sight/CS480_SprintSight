from datetime import datetime, timezone
from uuid import uuid4

from app.core.security import hash_password
from app.repositories.interfaces import (
    AssessmentRepository,
    AuditRepository,
    DocumentRecord,
    DocumentRepository,
    IngestionMetricBundle,
    JiraIngestionRunRecord,
    JiraIngestionRunRepository,
    ManualTextRepository,
    MetricsRepository,
    OverrideRepository,
    UserRecord,
    UserRepository,
    CourseRecord,
    ProjectRecord,
    ProjectRepository,
)
from app.schemas.assessment import AssessmentReport, AuditRecord, JiraCleanedSnapshot, ManualTextPayload, OverrideResponse
from app.schemas.auth import Role


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._revoked_tokens: set[str] = set()
        self._users = {
            "faculty@sprintsight.edu": UserRecord(
                id="u-faculty-1",
                email="faculty@sprintsight.edu",
                full_name="Faculty User",
                role=Role.INSTRUCTOR,
                hashed_password=hash_password("password123"),
            ),
            "admin@sprintsight.edu": UserRecord(
                id="u-admin-1",
                email="admin@sprintsight.edu",
                full_name="Admin User",
                role=Role.ADMIN,
                hashed_password=hash_password("password123"),
            ),
            "student@sprintsight.edu": UserRecord(
                id="u-student-1",
                email="student@sprintsight.edu",
                full_name="Student User",
                role=Role.STUDENT,
                hashed_password=hash_password("password123"),
            ),
        }

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._users.get(email.lower())

    def get_by_id(self, user_id: str) -> UserRecord | None:
        for user in self._users.values():
            if user.id == user_id:
                return user
        return None

    def record_login(self, user_id: str) -> None:
        return None

    def revoke_access_token(self, token_id: str, user_id: str, expires_at: datetime) -> None:
        self._revoked_tokens.add(token_id)

    def is_access_token_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked_tokens

    def list_users(self) -> list[UserRecord]:
        return list(self._users.values())

    def create_user(self, user: UserRecord) -> UserRecord:
        self._users[user.email.lower()] = user
        return user

    def update_user(self, user_id: str, email: str, full_name: str, role: Role, is_active: bool) -> UserRecord | None:
        user = self.get_by_id(user_id)
        if not user:
            return None
        old_email = user.email.lower()
        user.email = email.lower()
        user.full_name = full_name
        user.role = role
        user.is_active = is_active
        if old_email != user.email:
            del self._users[old_email]
        self._users[user.email] = user
        return user

    def update_password(self, user_id: str, hashed_password: str, must_change_password: bool) -> UserRecord | None:
        user = self.get_by_id(user_id)
        if not user:
            return None
        user.hashed_password = hashed_password
        user.must_change_password = must_change_password
        user.token_version += 1
        return user


class InMemoryProjectRepository(ProjectRepository):
    def __init__(self) -> None:
        self._courses: dict[str, CourseRecord] = {}
        self._projects: dict[str, ProjectRecord] = {}
        self._instructors: set[tuple[str, str]] = set()
        self._enrollments: set[tuple[str, str]] = set()
        self._members: dict[str, list[str]] = {}

    def create_course(self, code: str, name: str, section: str, year: int, term: str, created_by: str) -> CourseRecord:
        course = CourseRecord(str(uuid4()), code.upper(), name, section, year, term, created_by, now_utc())
        self._courses[course.id] = course
        self._instructors.add((course.id, created_by))
        return course

    def get_course(self, course_id: str) -> CourseRecord | None:
        return self._courses.get(course_id)

    def list_courses(self) -> list[CourseRecord]:
        return list(self._courses.values())

    def assign_instructor(self, course_id: str, user_id: str) -> None:
        self._instructors.add((course_id, user_id))
        
    def unassign_instructor(self, course_id: str, user_id: str) -> None:
        self._instructors.discard((course_id, user_id))

    def is_instructor_assigned(self, course_id: str, user_id: str) -> bool:
        return (course_id, user_id) in self._instructors

    def enroll_student(self, course_id: str, user_id: str) -> bool:
        if (course_id, user_id) in self._enrollments:
            return False
        course = self.get_course(course_id)
        if course and any(self.get_course(existing_course_id).code.lower() == course.code.lower()
                          for existing_course_id, existing_user_id in self._enrollments
                          if existing_user_id == user_id and self.get_course(existing_course_id)):
            return False
        self._enrollments.add((course_id, user_id))
        return True

    def is_student_enrolled(self, course_id: str, user_id: str) -> bool:
        return (course_id, user_id) in self._enrollments

    def unenroll_student(self, course_id: str, user_id: str) -> bool:
        enrollment = (course_id, user_id)
        if enrollment not in self._enrollments:
            return False
        self._enrollments.remove(enrollment)
        return True

    def list_enrolled_student_ids(self, course_id: str) -> list[str]:
        return [user_id for enrolled_course_id, user_id in self._enrollments if enrolled_course_id == course_id]

    def list_student_course_codes(self, user_id: str) -> list[str]:
        return [self._courses[course_id].code for course_id, enrolled_user_id in self._enrollments
                if enrolled_user_id == user_id]

    def update_course(self, course_id: str, code: str, name: str, section: str, year: int, term: str) -> CourseRecord | None:
        course = self._courses.get(course_id)
        if not course:
            return None
        course.code, course.name, course.section, course.year, course.term = code.upper(), name, section, year, term
        return course

    def delete_course(self, course_id: str) -> CourseRecord | None:
        course = self._courses.pop(course_id, None)
        self._instructors = {(cid, uid) for cid, uid in self._instructors if cid != course_id}
        self._enrollments = {(cid, uid) for cid, uid in self._enrollments if cid != course_id}
        return course

    def create_project(self, project: ProjectRecord, member_ids: list[str]) -> ProjectRecord:
        self._projects[project.id] = project
        self._members[project.id] = list(dict.fromkeys(member_ids))
        return project

    def get_project(self, project_id: str) -> ProjectRecord | None:
        return self._projects.get(project_id)

    def list_projects(self, course_id: str) -> list[ProjectRecord]:
        return [project for project in self._projects.values() if project.course_id == course_id]

    def update_project(
        self,
        project_id: str,
        project_name: str,
        team_name: str,
        description: str | None,
        github_repo_url: str | None,
        local_repo_path: str | None,
        jira_email: str | None,
        jira_domain: str | None,
        jira_project_key: str | None,
        jira_api_token_encrypted: str | None,
    ) -> ProjectRecord | None:
        project = self._projects.get(project_id)
        if not project:
            return None
        project.project_name = project_name
        project.team_name = team_name
        project.description = description
        project.github_repo_url = github_repo_url
        project.local_repo_path = local_repo_path
        project.jira_email = jira_email
        project.jira_domain = jira_domain
        project.jira_project_key = jira_project_key
        project.jira_api_token_encrypted = jira_api_token_encrypted
        return project

    def delete_project(self, project_id: str) -> ProjectRecord | None:
        project = self._projects.pop(project_id, None)
        self._members.pop(project_id, None)
        return project

    def set_members(self, project_id: str, member_ids: list[str]) -> None:
        self._members[project_id] = list(dict.fromkeys(member_ids))

    def list_member_ids(self, project_id: str) -> list[str]:
        return self._members.get(project_id, [])

class InMemoryManualTextRepository(ManualTextRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], str] = {}

    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None:
        key = (payload.course_id, payload.project_id, payload.sprint_id)
        cleaned = " ".join(payload.expectations_text.split())
        self._store[key] = f"{cleaned}\n\n(Updated by {updated_by})"

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None:
        return self._store.get((course_id, project_id, sprint_id))


class InMemoryDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self._documents: dict[str, DocumentRecord] = {}

    def create_document(self, document: DocumentRecord) -> DocumentRecord:
        self._documents[document.id] = document
        return document

    def list_documents(self, project_id: str) -> list[DocumentRecord]:
        return sorted(
            (document for document in self._documents.values() if document.project_id == project_id),
            key=lambda document: (document.created_at, document.id),
        )

    def get_document(self, project_id: str, document_id: str) -> DocumentRecord | None:
        document = self._documents.get(document_id)
        return document if document and document.project_id == project_id else None


class InMemoryAssessmentRepository(AssessmentRepository):
    def __init__(self) -> None:
        self._reports: dict[str, AssessmentReport] = {}

    def save_report(self, report: AssessmentReport) -> None:
        self._reports[report.report_id] = report

    def get_report(self, report_id: str) -> AssessmentReport | None:
        return self._reports.get(report_id)

    def get_latest_report(self, course_id: str, project_id: str, sprint_id: str) -> AssessmentReport | None:
        matching = [
            report
            for report in self._reports.values()
            if report.course_id == course_id
            and report.project_id == project_id
            and report.sprint_id == sprint_id
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda report: report.generated_at)[-1]


class InMemoryOverrideRepository(OverrideRepository):
    def __init__(self) -> None:
        self._overrides: list[OverrideResponse] = []

    def save_override(self, record: OverrideResponse) -> None:
        self._overrides.append(record)

    def list_overrides(self) -> list[OverrideResponse]:
        return list(self._overrides)


class InMemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._audits: list[AuditRecord] = []

    def save_audit(self, record: AuditRecord) -> None:
        self._audits.append(record)

    def list_audits(self) -> list[AuditRecord]:
        return list(self._audits)


class InMemoryJiraIngestionRunRepository(JiraIngestionRunRepository):
    def __init__(self) -> None:
        self._runs: dict[str, JiraIngestionRunRecord] = {}

    def create_run(self, run: JiraIngestionRunRecord) -> JiraIngestionRunRecord:
        self._runs[run.id] = run
        return run

    def get_run(self, project_id: str, sprint_id: str, run_id: str) -> JiraIngestionRunRecord | None:
        run = self._runs.get(run_id)
        if not run or run.project_id != project_id or run.sprint_id != sprint_id:
            return None
        return run

    def list_project_runs(self, project_id: str) -> list[JiraIngestionRunRecord]:
        return sorted(
            (run for run in self._runs.values() if run.project_id == project_id),
            key=lambda run: (run.captured_at, run.id),
            reverse=True,
        )

    def list_runs(self, project_id: str, sprint_id: str) -> list[JiraIngestionRunRecord]:
        return sorted(
            (run for run in self._runs.values() if run.project_id == project_id and run.sprint_id == sprint_id),
            key=lambda run: (run.captured_at, run.id),
            reverse=True,
        )

    def update_processed_run(
        self,
        project_id: str,
        sprint_id: str,
        run_id: str,
        status: str,
        processed_at: datetime | None,
        normalization_version: str | None,
        processing_error: str | None,
        cleaned_snapshot: JiraCleanedSnapshot | None,
    ) -> JiraIngestionRunRecord | None:
        run = self.get_run(project_id, sprint_id, run_id)
        if not run:
            return None
        run.processing_status = status
        run.processed_at = processed_at
        run.normalization_version = normalization_version
        run.processing_error = processing_error
        run.cleaned_snapshot = cleaned_snapshot
        return run


class InMemoryMetricsRepository(MetricsRepository):
    def __init__(self) -> None:
        self._metrics: dict[tuple[str, str, str], IngestionMetricBundle] = {}

    def save_metrics(self, metrics: IngestionMetricBundle) -> None:
        key = (metrics.course_id, metrics.project_id, metrics.sprint_id)
        self._metrics[key] = metrics

    def get_metrics(self, course_id: str, project_id: str, sprint_id: str) -> IngestionMetricBundle | None:
        return self._metrics.get((course_id, project_id, sprint_id))

    def get_metrics_page(self, course_id: str, project_id: str, sprint_id: str, limit: int, offset: int) -> tuple[IngestionMetricBundle | None, int]:
        metrics = self.get_metrics(course_id, project_id, sprint_id)
        if not metrics:
            return None, 0
        ordered_commits = sorted(metrics.commits, key=lambda commit: (commit.timestamp, commit.sha))
        page = ordered_commits[offset:offset + limit]
        return IngestionMetricBundle(
            course_id=metrics.course_id,
            project_id=metrics.project_id,
            sprint_id=metrics.sprint_id,
            commit_frequency=metrics.commit_frequency,
            code_churn=metrics.code_churn,
            pr_turnaround_hours=metrics.pr_turnaround_hours,
            assigned_story_points=metrics.assigned_story_points,
            completion_percent=metrics.completion_percent,
            commits=page,
            local_repo_path=metrics.local_repo_path,
            head_sha=metrics.head_sha,
            captured_at=metrics.captured_at,
        ), len(ordered_commits)


users_repo = InMemoryUserRepository()
manual_text_repo = InMemoryManualTextRepository()
assessment_repo = InMemoryAssessmentRepository()
overrides_repo = InMemoryOverrideRepository()
audit_repo = InMemoryAuditRepository()
metrics_repo = InMemoryMetricsRepository()
projects_repo = InMemoryProjectRepository()
jira_ingestion_repo = InMemoryJiraIngestionRunRepository()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
