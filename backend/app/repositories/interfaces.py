from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.schemas.auth import Role
from app.schemas.assessment import AssessmentReport, AuditRecord, ManualTextPayload, OverrideResponse


@dataclass
class UserRecord:
    id: str
    email: str
    full_name: str
    role: Role
    hashed_password: str
    is_active: bool = True


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> UserRecord | None: ...

    def get_by_id(self, user_id: str) -> UserRecord | None: ...

    def record_login(self, user_id: str) -> None: ...

    def revoke_access_token(self, token_id: str, user_id: str, expires_at: datetime) -> None: ...

    def is_access_token_revoked(self, token_id: str) -> bool: ...


class ManualTextRepository(Protocol):
    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None: ...

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None: ...


class AssessmentRepository(Protocol):
    def save_report(self, report: AssessmentReport) -> None: ...

    def get_report(self, report_id: str) -> AssessmentReport | None: ...

    def get_latest_report(self, course_id: str, project_id: str, sprint_id: str) -> AssessmentReport | None: ...


class OverrideRepository(Protocol):
    def save_override(self, record: OverrideResponse) -> None: ...

    def list_overrides(self) -> list[OverrideResponse]: ...


class AuditRepository(Protocol):
    def save_audit(self, record: AuditRecord) -> None: ...

    def list_audits(self) -> list[AuditRecord]: ...


@dataclass
class IngestionMetricBundle:
    course_id: str
    project_id: str
    sprint_id: str
    commit_frequency: float
    code_churn: int
    pr_turnaround_hours: float
    assigned_story_points: int
    completion_percent: float
    captured_at: datetime


class MetricsRepository(Protocol):
    def save_metrics(self, metrics: IngestionMetricBundle) -> None: ...

    def get_metrics(self, course_id: str, project_id: str, sprint_id: str) -> IngestionMetricBundle | None: ...
