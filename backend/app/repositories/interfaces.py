from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.auth import Role
from app.schemas.assessment import (
    AssessRequest,
    AssessmentJobEvent,
    AssessmentJobRecord,
    AssessmentReport,
    AuditRecord,
    CommitInfo,
    JiraCleanedSnapshot,
    ManualTextPayload,
    OverrideResponse,
)


@dataclass
class UserRecord:
    id: str
    email: str
    full_name: str
    role: Role
    hashed_password: str
    is_active: bool = True
    must_change_password: bool = False
    token_version: int = 0


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def record_login(self, user_id: str) -> None: ...

    def revoke_access_token(self, token_id: str, user_id: str, expires_at: datetime) -> None: ...

    def is_access_token_revoked(self, token_id: str) -> bool: ...

    def list_users(self) -> list[UserRecord]: ...

    def create_user(self, user: UserRecord) -> UserRecord: ...

    def update_user(self, user_id: str, email: str, full_name: str, role: Role, is_active: bool) -> UserRecord | None: ...

    def update_password(self, user_id: str, hashed_password: str, must_change_password: bool) -> UserRecord | None: ...


@dataclass
class CourseRecord:
    id: str
    code: str
    name: str
    section: str
    year: int
    term: str
    created_by: str
    created_at: datetime


@dataclass
class ProjectRecord:
    id: str
    project_name: str
    team_name: str
    description: str | None
    course_id: str
    course_code: str
    github_repo_url: str | None
    local_repo_path: str | None
    created_by: str
    created_at: datetime
    jira_email: str | None = None
    jira_domain: str | None = None
    jira_project_key: str | None = None
    jira_api_token_encrypted: str | None = None


class ProjectRepository(Protocol):
    def create_course(self, code: str, name: str, section: str, year: int, term: str, created_by: str) -> CourseRecord: ...
    def get_course(self, course_id: str) -> CourseRecord | None: ...
    def list_courses(self) -> list[CourseRecord]: ...
    def assign_instructor(self, course_id: str, user_id: str) -> None: ...
    def is_instructor_assigned(self, course_id: str, user_id: str) -> bool: ...
    def create_project(self, project: ProjectRecord, member_ids: list[str]) -> ProjectRecord: ...
    def unassign_instructor(self, course_id: str, user_id: str) -> None: ...
    def get_project(self, project_id: str) -> ProjectRecord | None: ...
    def list_projects(self, course_id: str) -> list[ProjectRecord]: ...
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
    ) -> ProjectRecord | None: ...
    def delete_project(self, project_id: str) -> ProjectRecord | None: ...
    def set_members(self, project_id: str, member_ids: list[str]) -> None: ...
    def list_member_ids(self, project_id: str) -> list[str]: ...
    def enroll_student(self, course_id: str, user_id: str) -> bool: ...
    def unenroll_student(self, course_id: str, user_id: str) -> bool: ...
    def is_student_enrolled(self, course_id: str, user_id: str) -> bool: ...
    def list_enrolled_student_ids(self, course_id: str) -> list[str]: ...
    def list_student_course_codes(self, user_id: str) -> list[str]: ...
    def update_course(self, course_id: str, code: str, name: str, section: str, year: int, term: str) -> CourseRecord | None: ...
    def delete_course(self, course_id: str) -> CourseRecord | None: ...


@dataclass
class DocumentRecord:
    id: str
    project_id: str
    filename: str
    mime_type: str
    byte_size: int
    checksum: str
    storage_bucket: str
    storage_key: str
    uploaded_by: str
    created_at: datetime


class DocumentRepository(Protocol):
    def create_document(self, document: DocumentRecord) -> DocumentRecord: ...

    def list_documents(self, project_id: str) -> list[DocumentRecord]: ...

    def get_document(self, project_id: str, document_id: str) -> DocumentRecord | None: ...


class ManualTextRepository(Protocol):
    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None: ...

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None: ...


class AssessmentRepository(Protocol):
    def save_report(self, report: AssessmentReport) -> None: ...

    def get_report(self, report_id: str) -> AssessmentReport | None: ...

    def update_manual_assessment(self, report_id: str, patch: dict[str, object]) -> AssessmentReport | None: ...

    def list_reports(self, course_id: str, project_id: str, sprint_id: str) -> list[AssessmentReport]: ...

    def list_project_reports(self, course_id: str, project_id: str) -> list[AssessmentReport]: ...

    def get_latest_report(self, course_id: str, project_id: str, sprint_id: str) -> AssessmentReport | None: ...


class AssessmentJobRepository(Protocol):
    def create_job(self, payload: AssessRequest) -> AssessmentJobRecord: ...

    def get_job(self, job_id: str) -> AssessmentJobRecord | None: ...

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        current_stage: str | None = None,
        report_id: str | None = None,
        error_message: str | None = None,
    ) -> AssessmentJobRecord | None: ...

    def append_event(self, job_id: str, event: str, data: dict) -> None: ...

    def list_events(self, job_id: str) -> list[AssessmentJobEvent]: ...


@dataclass
class RubricWeightsRecord:
    course_id: str
    weights: dict[str, float]
    updated_by: str
    updated_at: datetime


class RubricWeightsRepository(Protocol):
    def get_weights(self, course_id: str) -> RubricWeightsRecord | None: ...

    def set_weights(self, course_id: str, weights: dict[str, float], updated_by: str) -> RubricWeightsRecord: ...


class OverrideRepository(Protocol):
    def save_override(self, record: OverrideResponse) -> None: ...

    def list_overrides(self) -> list[OverrideResponse]: ...


class AuditRepository(Protocol):
    def save_audit(self, record: AuditRecord) -> None: ...

    def list_audits(self) -> list[AuditRecord]: ...

    def list_audits_before(self, cutoff: datetime, limit: int) -> list[AuditRecord]: ...

    def delete_audits(self, override_ids: list[str]) -> int: ...


class ActionAuditRepository(Protocol):
    def save_action_audit(self, record: object) -> None: ...

    def list_action_audits(self) -> list[object]: ...

    def list_action_audits_before(self, cutoff: datetime, limit: int) -> list[object]: ...

    def delete_action_audits(self, audit_ids: list[str]) -> int: ...


@dataclass
class IngestionMetricBundle:
    course_id: str
    project_id: str
    sprint_id: str
    commit_frequency: float
    code_churn: int
    pr_turnaround_hours: float | None
    assigned_story_points: int | None
    completion_percent: float | None
    commits: list[CommitInfo]
    local_repo_path: str | None
    head_sha: str | None
    captured_at: datetime


class MetricsRepository(Protocol):
    def save_metrics(self, metrics: IngestionMetricBundle) -> None: ...

    def get_metrics(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> IngestionMetricBundle | None: ...

    def get_metrics_page(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        limit: int,
        offset: int,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> tuple[IngestionMetricBundle | None, int]: ...


@dataclass
class JiraIngestionRunRecord:
    id: str
    course_id: str
    project_id: str
    sprint_id: str
    jira_project_key: str
    jql: str
    raw_bucket: str
    raw_object_key: str
    issue_count: int
    captured_at: datetime
    processed_at: datetime | None = None
    processing_status: str = "pending"
    normalization_version: str | None = None
    processing_error: str | None = None
    cleaned_snapshot: JiraCleanedSnapshot | None = None


class JiraIngestionRunRepository(Protocol):
    def create_run(self, run: JiraIngestionRunRecord) -> JiraIngestionRunRecord: ...

    def get_run(self, project_id: str, sprint_id: str, run_id: str) -> JiraIngestionRunRecord | None: ...

    def list_project_runs(self, project_id: str) -> list[JiraIngestionRunRecord]: ...

    def list_runs(self, project_id: str, sprint_id: str) -> list[JiraIngestionRunRecord]: ...

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
    ) -> JiraIngestionRunRecord | None: ...
