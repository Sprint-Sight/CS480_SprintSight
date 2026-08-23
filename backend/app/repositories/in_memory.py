from datetime import datetime, timezone

from app.core.security import hash_password
from app.repositories.interfaces import (
    AssessmentRepository,
    AuditRepository,
    IngestionMetricBundle,
    ManualTextRepository,
    MetricsRepository,
    OverrideRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.assessment import AssessmentReport, AuditRecord, ManualTextPayload, OverrideResponse
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


class InMemoryManualTextRepository(ManualTextRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str], str] = {}

    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None:
        key = (payload.course_id, payload.project_id, payload.sprint_id)
        cleaned = " ".join(payload.expectations_text.split())
        self._store[key] = f"{cleaned}\n\n(Updated by {updated_by})"

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None:
        return self._store.get((course_id, project_id, sprint_id))


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


class InMemoryMetricsRepository(MetricsRepository):
    def __init__(self) -> None:
        self._metrics: dict[tuple[str, str, str], IngestionMetricBundle] = {}

    def save_metrics(self, metrics: IngestionMetricBundle) -> None:
        key = (metrics.course_id, metrics.project_id, metrics.sprint_id)
        self._metrics[key] = metrics

    def get_metrics(self, course_id: str, project_id: str, sprint_id: str) -> IngestionMetricBundle | None:
        return self._metrics.get((course_id, project_id, sprint_id))


users_repo = InMemoryUserRepository()
manual_text_repo = InMemoryManualTextRepository()
assessment_repo = InMemoryAssessmentRepository()
overrides_repo = InMemoryOverrideRepository()
audit_repo = InMemoryAuditRepository()
metrics_repo = InMemoryMetricsRepository()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
