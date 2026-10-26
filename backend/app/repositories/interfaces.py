from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.assessment import (
    AssessmentJobEvent,
    AssessmentJobRecord,
    AssessmentReport,
    AssessRequest,
    AuditRecord,
    CommitInfo,
    JiraCleanedSnapshot,
    ManualTextPayload,
    OverrideResponse,
)
from app.schemas.auth import Role


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
    student_number: int | None = None


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def get_by_student_number(self, student_number: int) -> UserRecord | None: ...

    def set_student_number(self, user_id: str, student_number: int) -> UserRecord | None: ...

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
    def remove_student_from_projects_in_course(self, course_id: str, user_id: str) -> None: ...
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

    def delete_document(self, project_id: str, document_id: str) -> DocumentRecord | None: ...


@dataclass
class NotificationRecord:
    id: str
    recipient_id: str
    event_type: str
    title: str
    message: str
    created_at: datetime
    read_at: datetime | None = None


class NotificationRepository(Protocol):
    def create_notification(self, notification: NotificationRecord) -> NotificationRecord: ...

    def list_notifications(self, recipient_id: str, limit: int = 50) -> list[NotificationRecord]: ...

    def count_unread_notifications(self, recipient_id: str) -> int: ...

    def mark_notification_read(
        self, notification_id: str, recipient_id: str
    ) -> NotificationRecord | None: ...


@dataclass
class EmailOutboxRecord:
    """A single outbound email waiting to be delivered by the dispatcher."""

    id: str
    recipient: str
    subject: str
    body: str
    kind: str
    status: str
    attempts: int
    created_at: datetime
    scheduled_for: datetime
    sent_at: datetime | None = None
    last_error: str | None = None


class EmailOutboxRepository(Protocol):
    def enqueue_email(self, record: EmailOutboxRecord) -> EmailOutboxRecord: ...

    def claim_due_emails(self, now: datetime, limit: int) -> list[EmailOutboxRecord]: ...

    def mark_email_sent(self, email_id: str, sent_at: datetime) -> None: ...

    def mark_email_failed(
        self, email_id: str, error: str, retry_after: datetime | None
    ) -> None: ...

    def requeue_stale_emails(self, cutoff: datetime) -> int: ...

    def count_emails_sent_since(self, since: datetime) -> int: ...

    def list_emails(self, limit: int = 50) -> list[EmailOutboxRecord]: ...


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


@dataclass
class InstructorModelSelectionRecord:
    # The AI model an instructor has chosen as their default. Keyed per
    # instructor (user_id), not per course. `model_id` is the value sent to
    # the AI engine as model_name.
    user_id: str
    model_id: str
    updated_at: datetime


class InstructorModelSelectionRepository(Protocol):
    def get_selection(self, user_id: str) -> InstructorModelSelectionRecord | None: ...

    def set_selection(self, user_id: str, model_id: str) -> InstructorModelSelectionRecord: ...


@dataclass
class InstructorJiraCredentialsRecord:
    user_id: str
    jira_email: str | None
    jira_api_token_encrypted: str | None
    updated_at: datetime


class InstructorJiraCredentialsRepository(Protocol):
    def get_credentials(self, user_id: str) -> InstructorJiraCredentialsRecord | None: ...

    def set_credentials(
        self,
        user_id: str,
        jira_email: str | None,
        jira_api_token_encrypted: str | None,
    ) -> InstructorJiraCredentialsRecord: ...


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
class AuditRetentionConfig:
    hot_retention_days: int
    action_archive_retention_days: int
    override_archive_retention_days: int
    updated_at: datetime
    updated_by: str | None


class AuditRetentionConfigRepository(Protocol):
    def get_config(self) -> AuditRetentionConfig: ...

    def update_config(
        self,
        hot_retention_days: int,
        action_archive_retention_days: int,
        override_archive_retention_days: int,
        updated_by: str,
    ) -> AuditRetentionConfig: ...


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


@dataclass
class ExportLogRecord:
    log_id: str
    user_id: str
    report_type: str  # "pdf" or "csv"
    course_id: str
    project_id: str
    sprint_id: str
    include_student_emails: bool
    download_token: str
    expires_at: datetime
    created_at: datetime


class ExportLogRepository(Protocol):
    def create_log(self, record: ExportLogRecord) -> ExportLogRecord: ...

    def get_log(self, download_token: str) -> ExportLogRecord | None: ...

    def list_logs(self, user_id: str, limit: int = 50) -> list[ExportLogRecord]: ...

    def count_exports_since(
        self, user_id: str, since: datetime
    ) -> int: ...


@dataclass
class PeerEvaluationRecord:
    evaluation_id: str
    course_id: str
    project_id: str
    rater_id: str          # The student who submitted the evaluation
    rated_id: str          # The student being evaluated
    score: int             # 1-5
    remarks: str | None    # Optional remarks
    created_at: datetime
    reason: str | None = None  # Why the score was given


@dataclass
class PeerEvaluationConfigRecord:
    course_id: str
    is_open: bool
    updated_by: str
    updated_at: datetime
    opens_at: datetime | None = None
    expires_at: datetime | None = None


class PeerEvaluationRepository(Protocol):
    def save_evaluation(self, evaluation: PeerEvaluationRecord) -> PeerEvaluationRecord: ...

    def get_evaluation(self, evaluation_id: str) -> PeerEvaluationRecord | None: ...

    def list_evaluations_by_rater(
        self, rater_id: str, project_id: str | None = None
    ) -> list[PeerEvaluationRecord]: ...

    def list_evaluations_by_project(
        self, project_id: str
    ) -> list[PeerEvaluationRecord]: ...

    def list_evaluations_by_course(
        self, course_id: str
    ) -> list[PeerEvaluationRecord]: ...

    def get_evaluation_by_rater_and_rated(
        self, rater_id: str, rated_id: str, project_id: str
    ) -> PeerEvaluationRecord | None: ...

    def save_config(self, config: PeerEvaluationConfigRecord) -> PeerEvaluationConfigRecord: ...

    def get_config(self, course_id: str) -> PeerEvaluationConfigRecord | None: ...

    def delete_evaluation(self, evaluation_id: str) -> bool: ...
