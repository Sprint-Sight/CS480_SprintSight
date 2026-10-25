from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from app.repositories.interfaces import (
    AssessmentRepository,
    AuditRetentionConfig,
    AuditRetentionConfigRepository,
    CourseRecord,
    DocumentRecord,
    DocumentRepository,
    EmailOutboxRecord,
    EmailOutboxRepository,
    IngestionMetricBundle,
    InstructorModelSelectionRecord,
    InstructorModelSelectionRepository,
    JiraIngestionRunRecord,
    JiraIngestionRunRepository,
    ManualTextRepository,
    MetricsRepository,
    NotificationRecord,
    NotificationRepository,
    PeerEvaluationConfigRecord,
    PeerEvaluationRecord,
    PeerEvaluationRepository,
    ProjectRecord,
    ProjectRepository,
    RubricWeightsRecord,
    RubricWeightsRepository,
    UserRecord,
    UserRepository,
)
from app.schemas.assessment import (
    ActionAuditRecord,
    AssessmentReport,
    AuditRecord,
    JiraCleanedSnapshot,
    ManualTextPayload,
)
from app.schemas.auth import Role

_PROJECT_COLUMNS = """p.project_id, p.project_name, p.team_name, p.description, p.course_id, c.code AS course_code,
    p.github_repo_url, p.local_repo_path, p.created_by, p.created_at,
    p.jira_email, p.jira_domain, p.jira_project_key, p.jira_api_token_encrypted"""


def ensure_user_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS student_number BIGINT")
        connection.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_users_student_number
               ON users(student_number) WHERE student_number IS NOT NULL"""
        )


def ensure_project_credential_schema(pool: ConnectionPool) -> None:
    statements = (
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_name VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_email VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_domain VARCHAR(255)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_project_key VARCHAR(50)",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS jira_api_token_encrypted TEXT",
    )
    with pool.connection() as connection:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS project_documents (
                document_id UUID PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                uploader_id UUID NOT NULL REFERENCES users(user_id),
                filename VARCHAR(255) NOT NULL,
                mime_type VARCHAR(100) NOT NULL,
                byte_size BIGINT NOT NULL CHECK (byte_size > 0),
                checksum VARCHAR(64) NOT NULL,
                storage_bucket VARCHAR(255) NOT NULL,
                storage_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_project_documents_project_id ON project_documents(project_id)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS jira_ingestion_runs (
                run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                jira_project_key VARCHAR(50) NOT NULL,
                jql TEXT NOT NULL,
                raw_bucket VARCHAR(255) NOT NULL,
                raw_object_key TEXT NOT NULL UNIQUE,
                issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
                captured_at TIMESTAMPTZ NOT NULL,
                processed_at TIMESTAMPTZ,
                processing_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (processing_status IN ('pending', 'completed', 'failed')),
                normalization_version VARCHAR(50),
                processing_error TEXT,
                cleaned_snapshot JSONB CHECK (cleaned_snapshot IS NULL OR jsonb_typeof(cleaned_snapshot) = 'object')
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_runs_project_sprint_captured "
            "ON jira_ingestion_runs(project_id, sprint_id, captured_at DESC)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS manual_text (
                manual_text_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                expectations_text TEXT NOT NULL CHECK (length(btrim(expectations_text)) BETWEEN 1 AND 5000),
                updated_by UUID NOT NULL REFERENCES users(user_id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (course_id, project_id, sprint_id),
                FOREIGN KEY (project_id, course_id) REFERENCES projects(project_id, course_id) ON DELETE CASCADE
            )"""
        )


def ensure_notification_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS user_notifications (
                notification_id UUID PRIMARY KEY,
                recipient_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                event_type VARCHAR(80) NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMPTZ
            )"""
        )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_user_notifications_recipient_created
               ON user_notifications(recipient_id, created_at DESC)"""
        )


def ensure_email_outbox_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS email_outbox (
                email_id UUID PRIMARY KEY,
                recipient VARCHAR(320) NOT NULL,
                subject VARCHAR(500) NOT NULL,
                body TEXT NOT NULL,
                kind VARCHAR(80) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                scheduled_for TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMPTZ,
                last_error TEXT
            )"""
        )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_email_outbox_pending
               ON email_outbox(status, scheduled_for)"""
        )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_email_outbox_sent_at
               ON email_outbox(sent_at DESC)"""
        )


class PostgresEmailOutboxRepository(EmailOutboxRepository):
    """Durable outbound email queue backed by Postgres."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _email(row: dict) -> EmailOutboxRecord:
        return EmailOutboxRecord(
            id=str(row["email_id"]),
            recipient=row["recipient"],
            subject=row["subject"],
            body=row["body"],
            kind=row["kind"],
            status=row["status"],
            attempts=int(row["attempts"]),
            created_at=row["created_at"],
            scheduled_for=row["scheduled_for"],
            sent_at=row["sent_at"],
            last_error=row["last_error"],
        )

    def enqueue_email(self, record: EmailOutboxRecord) -> EmailOutboxRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO email_outbox
                   (email_id, recipient, subject, body, kind, status, attempts,
                    created_at, scheduled_for, sent_at, last_error)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING email_id, recipient, subject, body, kind, status,
                             attempts, created_at, scheduled_for, sent_at, last_error""",
                (
                    UUID(record.id),
                    record.recipient,
                    record.subject,
                    record.body,
                    record.kind,
                    record.status,
                    record.attempts,
                    record.created_at,
                    record.scheduled_for,
                    record.sent_at,
                    record.last_error,
                ),
            ).fetchone()
        return self._email(row)

    def claim_due_emails(self, now: datetime, limit: int) -> list[EmailOutboxRecord]:
        """Atomically move due messages to ``sending`` and hand them to the caller."""
        with self._pool.connection() as connection:
            rows = connection.execute(
                """UPDATE email_outbox
                   SET status = 'sending', attempts = attempts + 1, scheduled_for = %s
                   WHERE email_id IN (
                       SELECT email_id FROM email_outbox
                       WHERE status = 'pending' AND scheduled_for <= %s
                       ORDER BY scheduled_for, created_at
                       FOR UPDATE SKIP LOCKED
                       LIMIT %s
                   )
                   RETURNING email_id, recipient, subject, body, kind, status,
                             attempts, created_at, scheduled_for, sent_at, last_error""",
                (now, now, limit),
            ).fetchall()
        return [self._email(row) for row in rows]

    def mark_email_sent(self, email_id: str, sent_at: datetime) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE email_outbox
                   SET status = 'sent', sent_at = %s, last_error = NULL
                   WHERE email_id = %s""",
                (sent_at, UUID(email_id)),
            )

    def mark_email_failed(
        self, email_id: str, error: str, retry_after: datetime | None
    ) -> None:
        status = "pending" if retry_after else "failed"
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE email_outbox
                   SET status = %s, last_error = %s, scheduled_for = COALESCE(%s, scheduled_for)
                   WHERE email_id = %s""",
                (status, error[:2000], retry_after, UUID(email_id)),
            )

    def count_emails_sent_since(self, since: datetime) -> int:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS sent_count FROM email_outbox "
                "WHERE status = 'sent' AND sent_at IS NOT NULL AND sent_at >= %s",
                (since,),
            ).fetchone()
        return int(row["sent_count"])

    def requeue_stale_emails(self, cutoff: datetime) -> int:
        """Return messages abandoned mid-delivery to the pending pool."""
        with self._pool.connection() as connection:
            result = connection.execute(
                """UPDATE email_outbox
                   SET status = 'pending', scheduled_for = CURRENT_TIMESTAMP
                   WHERE status = 'sending' AND scheduled_for <= %s""",
                (cutoff,),
            )
        return int(result.rowcount or 0)

    def list_emails(self, limit: int = 50) -> list[EmailOutboxRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT email_id, recipient, subject, body, kind, status,
                          attempts, created_at, scheduled_for, sent_at, last_error
                   FROM email_outbox
                   ORDER BY created_at DESC, email_id DESC
                   LIMIT %s""",
                (limit,),
            ).fetchall()
        return [self._email(row) for row in rows]


class PostgresNotificationRepository(NotificationRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _notification(row: dict) -> NotificationRecord:
        return NotificationRecord(
            id=str(row["notification_id"]),
            recipient_id=str(row["recipient_id"]),
            event_type=row["event_type"],
            title=row["title"],
            message=row["message"],
            created_at=row["created_at"],
            read_at=row["read_at"],
        )

    def create_notification(self, notification: NotificationRecord) -> NotificationRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO user_notifications
                   (notification_id, recipient_id, event_type, title, message, created_at, read_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING notification_id, recipient_id, event_type, title, message,
                             created_at, read_at""",
                (
                    UUID(notification.id),
                    UUID(notification.recipient_id),
                    notification.event_type,
                    notification.title,
                    notification.message,
                    notification.created_at,
                    notification.read_at,
                ),
            ).fetchone()
        return self._notification(row)

    def list_notifications(self, recipient_id: str, limit: int = 50) -> list[NotificationRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT notification_id, recipient_id, event_type, title, message,
                          created_at, read_at
                   FROM user_notifications
                   WHERE recipient_id = %s
                   ORDER BY created_at DESC, notification_id DESC
                   LIMIT %s""",
                (UUID(recipient_id), limit),
            ).fetchall()
        return [self._notification(row) for row in rows]

    def count_unread_notifications(self, recipient_id: str) -> int:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS unread_count
                   FROM user_notifications
                   WHERE recipient_id = %s AND read_at IS NULL""",
                (UUID(recipient_id),),
            ).fetchone()
        return int(row["unread_count"])

    def mark_notification_read(
        self, notification_id: str, recipient_id: str
    ) -> NotificationRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE user_notifications
                   SET read_at = COALESCE(read_at, CURRENT_TIMESTAMP)
                   WHERE notification_id = %s AND recipient_id = %s
                   RETURNING notification_id, recipient_id, event_type, title, message,
                             created_at, read_at""",
                (UUID(notification_id), UUID(recipient_id)),
            ).fetchone()
        return self._notification(row) if row else None


def ensure_audit_schema(pool: ConnectionPool) -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS action_audit_events (
            audit_id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            actor_role TEXT NOT NULL CHECK (actor_role IN ('admin', 'instructor', 'student')),
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS override_audit_events (
            override_id TEXT PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL,
            instructor_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            report_id TEXT NOT NULL,
            original_score DOUBLE PRECISION NOT NULL,
            new_score DOUBLE PRECISION NOT NULL,
            reason_comment TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_action_audit_created_at "
        "ON action_audit_events(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_action_audit_actor_created "
        "ON action_audit_events(actor_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_override_audit_timestamp "
        "ON override_audit_events(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_override_audit_instructor_timestamp "
        "ON override_audit_events(instructor_id, timestamp DESC)",
        """CREATE OR REPLACE FUNCTION guard_audit_events_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'UPDATE'
               OR current_setting('sprintsight.audit_retention', true) IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION 'Audit rows are append-only; deletion is reserved for retention.';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql""",
        """DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_action_audit_immutable'
                  AND tgrelid = 'action_audit_events'::regclass
            ) THEN
                CREATE TRIGGER trg_action_audit_immutable
                BEFORE UPDATE OR DELETE ON action_audit_events
                FOR EACH ROW EXECUTE FUNCTION guard_audit_events_immutable();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'trg_override_audit_immutable'
                  AND tgrelid = 'override_audit_events'::regclass
            ) THEN
                CREATE TRIGGER trg_override_audit_immutable
                BEFORE UPDATE OR DELETE ON override_audit_events
                FOR EACH ROW EXECUTE FUNCTION guard_audit_events_immutable();
            END IF;
        END;
        $$""",
    )
    with pool.connection() as connection:
        for statement in statements:
            connection.execute(statement)


def ensure_audit_retention_config_schema(
    pool: ConnectionPool,
    hot_retention_days: int,
    action_archive_retention_days: int,
    override_archive_retention_days: int,
) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS audit_retention_config (
                config_id SMALLINT PRIMARY KEY CHECK (config_id = 1),
                hot_retention_days INTEGER NOT NULL CHECK (hot_retention_days >= 1),
                action_archive_retention_days INTEGER NOT NULL
                    CHECK (action_archive_retention_days >= 1),
                override_archive_retention_days INTEGER NOT NULL
                    CHECK (override_archive_retention_days >= 1),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO audit_retention_config (
                config_id, hot_retention_days, action_archive_retention_days,
                override_archive_retention_days
            ) VALUES (1, %s, %s, %s)
            ON CONFLICT (config_id) DO NOTHING""",
            (
                hot_retention_days,
                action_archive_retention_days,
                override_archive_retention_days,
            ),
        )


class PostgresAuditRetentionConfigRepository(AuditRetentionConfigRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _config(row: dict) -> AuditRetentionConfig:
        return AuditRetentionConfig(
            hot_retention_days=row["hot_retention_days"],
            action_archive_retention_days=row["action_archive_retention_days"],
            override_archive_retention_days=row["override_archive_retention_days"],
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
        )

    def get_config(self) -> AuditRetentionConfig:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT hot_retention_days, action_archive_retention_days,
                          override_archive_retention_days, updated_at, updated_by
                   FROM audit_retention_config WHERE config_id = 1"""
            ).fetchone()
        if row is None:
            raise RuntimeError("Audit retention configuration has not been initialized.")
        return self._config(row)

    def update_config(
        self,
        hot_retention_days: int,
        action_archive_retention_days: int,
        override_archive_retention_days: int,
        updated_by: str,
    ) -> AuditRetentionConfig:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE audit_retention_config
                   SET hot_retention_days = %s,
                       action_archive_retention_days = %s,
                       override_archive_retention_days = %s,
                       updated_at = CURRENT_TIMESTAMP,
                       updated_by = %s
                   WHERE config_id = 1
                   RETURNING hot_retention_days, action_archive_retention_days,
                             override_archive_retention_days, updated_at, updated_by""",
                (
                    hot_retention_days,
                    action_archive_retention_days,
                    override_archive_retention_days,
                    updated_by,
                ),
            ).fetchone()
        if row is None:
            raise RuntimeError("Audit retention configuration has not been initialized.")
        return self._config(row)


class PostgresAuditRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_audit(self, record: AuditRecord) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO override_audit_events
                (override_id, timestamp, instructor_id, student_id, report_id,
                 original_score, new_score, reason_comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (override_id) DO NOTHING""",
                (
                    record.override_id,
                    record.timestamp,
                    record.instructor_id,
                    record.student_id,
                    record.report_id,
                    record.original_score,
                    record.new_score,
                    record.reason_comment,
                ),
            )

    def list_audits(self) -> list[AuditRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT override_id, timestamp, instructor_id, student_id,
                          report_id, original_score, new_score, reason_comment
                   FROM override_audit_events ORDER BY timestamp DESC, override_id"""
            ).fetchall()
        return [
            AuditRecord.model_validate(row)
            for row in rows or []
        ]

    def list_audits_before(
        self,
        cutoff: datetime,
        limit: int,
    ) -> list[AuditRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT override_id, timestamp, instructor_id, student_id,
                          report_id, original_score, new_score, reason_comment
                   FROM override_audit_events WHERE timestamp < %s
                   ORDER BY timestamp, override_id LIMIT %s""",
                (cutoff, limit),
            ).fetchall()
        return [AuditRecord.model_validate(row) for row in rows or []]

    def delete_audits(self, override_ids: list[str]) -> int:
        if not override_ids:
            return 0
        with self._pool.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('sprintsight.audit_retention', 'on', true)"
                )
                cursor = connection.execute(
                    "DELETE FROM override_audit_events WHERE override_id = ANY(%s)",
                    (override_ids,),
                )
        return cursor.rowcount


class PostgresActionAuditRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_action_audit(self, record: ActionAuditRecord) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO action_audit_events
                (audit_id, actor_id, actor_role, action, target_type, target_id,
                 details, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (audit_id) DO NOTHING""",
                (
                    record.audit_id,
                    record.actor_id,
                    record.actor_role,
                    record.action,
                    record.target_type,
                    record.target_id,
                    Json(record.details),
                    record.created_at,
                ),
            )

    def list_action_audits(self) -> list[ActionAuditRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT audit_id, actor_id, actor_role, action, target_type,
                          target_id, details, created_at
                   FROM action_audit_events
                   ORDER BY created_at DESC, audit_id"""
            ).fetchall()
        return [ActionAuditRecord.model_validate(row) for row in rows or []]

    def list_action_audits_before(
        self,
        cutoff: datetime,
        limit: int,
    ) -> list[ActionAuditRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT audit_id, actor_id, actor_role, action, target_type,
                          target_id, details, created_at
                   FROM action_audit_events WHERE created_at < %s
                   ORDER BY created_at, audit_id LIMIT %s""",
                (cutoff, limit),
            ).fetchall()
        return [ActionAuditRecord.model_validate(row) for row in rows or []]

    def delete_action_audits(self, audit_ids: list[str]) -> int:
        if not audit_ids:
            return 0
        with self._pool.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "SELECT set_config('sprintsight.audit_retention', 'on', true)"
                )
                cursor = connection.execute(
                    "DELETE FROM action_audit_events WHERE audit_id = ANY(%s)",
                    (audit_ids,),
                )
        return cursor.rowcount


class PostgresUserRepository(UserRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number
                FROM users
                WHERE lower(email) = lower(%s)
                """,
                (email,),
            ).fetchone()
        return self._to_record(row) if row else None

    def get_by_id(self, user_id: str) -> UserRecord | None:
        try:
            parsed_id = UUID(user_id)
        except ValueError:
            return None

        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number
                FROM users
                WHERE user_id = %s
                """,
                (parsed_id,),
            ).fetchone()
        return self._to_record(row) if row else None

    def get_by_student_number(self, student_number: int) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT user_id, email, full_name, password_hash, role, is_active,
                       must_change_password, token_version, student_number
                FROM users
                WHERE student_number = %s
                """,
                (student_number,),
            ).fetchone()
        return self._to_record(row) if row else None

    def set_student_number(self, user_id: str, student_number: int) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE users SET student_number = %s
                   WHERE user_id = %s
                   RETURNING user_id, email, full_name, password_hash, role, is_active,
                             must_change_password, token_version, student_number""",
                (student_number, UUID(user_id)),
            ).fetchone()
        return self._to_record(row) if row else None

    def record_login(self, user_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s",
                (UUID(user_id),),
            )

    def revoke_access_token(self, token_id: str, user_id: str, expires_at: datetime) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO revoked_access_tokens (token_id, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (token_id) DO NOTHING
                """,
                (UUID(token_id), UUID(user_id), expires_at),
            )

    def is_access_token_revoked(self, token_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM revoked_access_tokens
                WHERE token_id = %s AND expires_at > CURRENT_TIMESTAMP
                """,
                (UUID(token_id),),
            ).fetchone()
        return row is not None

    def list_users(self) -> list[UserRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number FROM users ORDER BY email"
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def create_user(self, user: UserRecord) -> UserRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO users (user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number""",
                (UUID(user.id), user.email.lower(), user.full_name, user.hashed_password, user.role.value,
                 user.is_active, user.must_change_password, user.token_version, user.student_number),
            ).fetchone()
        return self._to_record(row)

    def update_user(self, user_id: str, email: str, full_name: str, role: Role, is_active: bool) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE users SET email = %s, full_name = %s, role = %s, is_active = %s
                WHERE user_id = %s
                RETURNING user_id, email, full_name, password_hash, role, is_active, must_change_password, token_version, student_number""",
                (email.lower(), full_name, role.value, is_active, UUID(user_id)),
            ).fetchone()
        return self._to_record(row) if row else None

    def update_password(self, user_id: str, hashed_password: str, must_change_password: bool) -> UserRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE users SET password_hash = %s, must_change_password = %s, token_version = token_version + 1
                WHERE user_id = %s
                RETURNING user_id, email, full_name, password_hash, role, is_active,
                          must_change_password, token_version, student_number""",
                (hashed_password, must_change_password, UUID(user_id)),
            ).fetchone()
        return self._to_record(row) if row else None

    @staticmethod
    def _to_record(row: tuple | dict) -> UserRecord:
        if not isinstance(row, dict):
            raise TypeError("Postgres user rows must use dict_row")
        return UserRecord(
            id=str(row["user_id"]),
            email=row["email"],
            full_name=row["full_name"],
            role=Role(row["role"]),
            hashed_password=row["password_hash"],
            is_active=row["is_active"],
            must_change_password=row["must_change_password"],
            token_version=row["token_version"],
            student_number=row.get("student_number"),
        )


class PostgresProjectRepository(ProjectRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def create_course(self, code: str, name: str, section: str, year: int, term: str, created_by: str) -> CourseRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                "INSERT INTO courses (code, name, section, year, term, created_by) VALUES (%s, %s, %s, %s, %s, %s) RETURNING course_id, code, name, section, year, term, created_by, created_at",
                (code.upper(), name, section, year, term, UUID(created_by)),
            ).fetchone()
            connection.execute("INSERT INTO course_instructors (course_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (row["course_id"], UUID(created_by)))
        return self._course(row)

    def get_course(self, course_id: str) -> CourseRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT course_id, code, name, section, year, term, created_by, created_at FROM courses WHERE course_id = %s", (UUID(course_id),)
            ).fetchone()
        return self._course(row) if row else None

    def list_courses(self) -> list[CourseRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT course_id, code, name, section, year, term, created_by, created_at FROM courses ORDER BY code, year, term, section").fetchall()
        return [self._course(row) for row in rows]

    @staticmethod
    def _course(row: dict) -> CourseRecord:
        return CourseRecord(str(row["course_id"]), row["code"], row["name"], row["section"], row["year"], row["term"], str(row["created_by"]), row["created_at"])

    def assign_instructor(self, course_id: str, user_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute("INSERT INTO course_instructors (course_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (UUID(course_id), UUID(user_id)))
            
    def unassign_instructor(self, course_id: str, user_id: str) -> None:   # ← add this
        with self._pool.connection() as connection:
            connection.execute(
                "DELETE FROM course_instructors WHERE course_id = %s AND user_id = %s",
                (UUID(course_id), UUID(user_id)),
            )

    def is_instructor_assigned(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1 FROM course_instructors WHERE course_id = %s AND user_id = %s", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def enroll_student(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            # A student can enroll in a course code only once, across terms and sections.
            row = connection.execute("""
                SELECT 1 FROM course_students cs
                JOIN courses c ON c.course_id = cs.course_id
                WHERE cs.user_id = %s
                AND lower(trim(c.code)) = lower(trim((SELECT code FROM courses WHERE course_id = %s)))
            """, (UUID(user_id), UUID(course_id))).fetchone()

            if row:
                return False

            inserted = connection.execute("""
                INSERT INTO course_students (course_id, user_id, code, term, year)
                SELECT %s, %s, c.code, c.term, c.year
                FROM courses c
                WHERE c.course_id = %s
                ON CONFLICT DO NOTHING
                RETURNING course_id
            """, (UUID(course_id), UUID(user_id), UUID(course_id))).fetchone()

        return inserted is not None

    def is_student_enrolled(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("SELECT 1 FROM course_students WHERE course_id = %s AND user_id = %s", (UUID(course_id), UUID(user_id))).fetchone()
        return row is not None

    def unenroll_student(self, course_id: str, user_id: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute("DELETE FROM course_students WHERE course_id = %s AND user_id = %s RETURNING course_id", (UUID(course_id), UUID(user_id))).fetchone()
        if row is None:
            return False
        self.remove_student_from_projects_in_course(course_id, user_id)
        return True

    def remove_student_from_projects_in_course(self, course_id: str, user_id: str) -> None:
        with self._pool.connection() as connection:
            project_rows = connection.execute(
                "SELECT project_id FROM projects WHERE course_id = %s",
                (UUID(course_id),),
            ).fetchall()
            for row in project_rows:
                project_id = str(row["project_id"])
                connection.execute(
                    "DELETE FROM project_members WHERE project_id = %s AND user_id = %s",
                    (UUID(project_id), UUID(user_id)),
                )

    def list_enrolled_student_ids(self, course_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT user_id FROM course_students WHERE course_id = %s ORDER BY enrolled_at", (UUID(course_id),)).fetchall()
        return [str(row["user_id"]) for row in rows]

    def list_student_course_codes(self, user_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT c.code FROM course_students cs JOIN courses c ON c.course_id = cs.course_id WHERE cs.user_id = %s", (UUID(user_id),)).fetchall()
        return [row["code"] for row in rows]

    def update_course(self, course_id: str, code: str, name: str, section: str, year: int, term: str) -> CourseRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute("""UPDATE courses SET code = %s, name = %s, section = %s, year = %s, term = %s
                WHERE course_id = %s RETURNING course_id, code, name, section, year, term, created_by, created_at""", (code.upper(), name, section, year, term, UUID(course_id))).fetchone()
        return self._course(row) if row else None

    def delete_course(self, course_id: str) -> CourseRecord | None:
        course = self.get_course(course_id)
        if course:
            with self._pool.connection() as connection:
                connection.execute("DELETE FROM courses WHERE course_id = %s", (UUID(course_id),))
        return course

    def create_project(self, project: ProjectRecord, member_ids: list[str]) -> ProjectRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO projects (
                    project_id, project_name, team_name, description, course_id,
                    github_repo_url, local_repo_path, created_by,
                    jira_email, jira_domain, jira_project_key, jira_api_token_encrypted
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING project_id, project_name, team_name, description, course_id,
                        github_repo_url, local_repo_path, created_by, created_at,
                        jira_email, jira_domain, jira_project_key, jira_api_token_encrypted""",
                (
                    UUID(project.id), project.project_name, project.team_name,
                    project.description, UUID(project.course_id),
                    project.github_repo_url, project.local_repo_path,
                    UUID(project.created_by), project.jira_email, project.jira_domain,
                    project.jira_project_key, project.jira_api_token_encrypted,
                ),
            ).fetchone()

            course = connection.execute(
                "SELECT code FROM courses WHERE course_id = %s",
                (UUID(project.course_id),)
            ).fetchone()
            row["course_code"] = course["code"]

            # ← FIX: include course_id in the insert
            for member_id in dict.fromkeys(member_ids):
                connection.execute(
                    """INSERT INTO project_members (project_id, course_id, user_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING""",
                    (UUID(project.id), UUID(project.course_id), UUID(member_id))
                )

        return self._project(row)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                f"""SELECT {_PROJECT_COLUMNS}
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.project_id = %s""",
                (UUID(project_id),),
            ).fetchone()
        return self._project(row) if row else None

    def list_projects(self, course_id: str) -> list[ProjectRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                f"""SELECT {_PROJECT_COLUMNS}
                FROM projects p JOIN courses c ON c.course_id = p.course_id WHERE p.course_id = %s ORDER BY p.project_name""",
                (UUID(course_id),),
            ).fetchall()
        return [self._project(row) for row in rows]

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
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE projects SET project_name = %s, team_name = %s, description = %s, github_repo_url = %s, local_repo_path = %s,
                    jira_email = %s, jira_domain = %s, jira_project_key = %s, jira_api_token_encrypted = %s
                WHERE project_id = %s RETURNING project_id, project_name, team_name, description, course_id, github_repo_url, local_repo_path, created_by, created_at, jira_email, jira_domain, jira_project_key, jira_api_token_encrypted""",
                (
                    project_name,
                    team_name,
                    description,
                    github_repo_url,
                    local_repo_path,
                    jira_email,
                    jira_domain,
                    jira_project_key,
                    jira_api_token_encrypted,
                    UUID(project_id),
                ),
            ).fetchone()
            if row:
                course = connection.execute("SELECT code FROM courses WHERE course_id = %s", (row["course_id"],)).fetchone()
                row["course_code"] = course["code"]
        return self._project(row) if row else None

    def delete_project(self, project_id: str) -> ProjectRecord | None:
        project = self.get_project(project_id)
        if project:
            with self._pool.connection() as connection:
                connection.execute("DELETE FROM projects WHERE project_id = %s", (UUID(project_id),))
        return project

    def set_members(self, project_id: str, member_ids: list[str]) -> None:
        with self._pool.connection() as connection:
            # Get course_id from the project first
            project_row = connection.execute(
                "SELECT course_id FROM projects WHERE project_id = %s",
                (UUID(project_id),)
            ).fetchone()

            if not project_row:
                raise ValueError(f"Project {project_id} not found")

            course_id = project_row["course_id"]

            connection.execute(
                "DELETE FROM project_members WHERE project_id = %s",
                (UUID(project_id),)
            )

            # ← FIX: include course_id in the insert
            for member_id in dict.fromkeys(member_ids):
                connection.execute(
                    """INSERT INTO project_members (project_id, course_id, user_id)
                    VALUES (%s, %s, %s)""",
                    (UUID(project_id), course_id, UUID(member_id))
                )

    def list_member_ids(self, project_id: str) -> list[str]:
        with self._pool.connection() as connection:
            rows = connection.execute("SELECT user_id FROM project_members WHERE project_id = %s", (UUID(project_id),)).fetchall()
        return [str(row["user_id"]) for row in rows]

    @staticmethod
    def _project(row: dict) -> ProjectRecord:
        return ProjectRecord(
            str(row["project_id"]),
            row["project_name"],
            row["team_name"],
            row["description"],
            str(row["course_id"]),
            row["course_code"],
            row["github_repo_url"],
            row["local_repo_path"],
            str(row["created_by"]),
            row["created_at"],
            row.get("jira_email"),
            row.get("jira_domain"),
            row.get("jira_project_key"),
            row.get("jira_api_token_encrypted"),
        )


class PostgresDocumentRepository(DocumentRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _document(row: dict) -> DocumentRecord:
        return DocumentRecord(
            id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            filename=row["filename"],
            mime_type=row["mime_type"],
            byte_size=row["byte_size"],
            checksum=row["checksum"],
            storage_bucket=row["storage_bucket"],
            storage_key=row["storage_key"],
            uploaded_by=str(row["uploader_id"]),
            created_at=row["created_at"],
        )

    def create_document(self, document: DocumentRecord) -> DocumentRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO project_documents
                (document_id, project_id, uploader_id, filename, mime_type, byte_size,
                 checksum, storage_bucket, storage_key, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at""",
                (UUID(document.id), UUID(document.project_id), UUID(document.uploaded_by),
                 document.filename, document.mime_type, document.byte_size, document.checksum,
                 document.storage_bucket, document.storage_key, document.created_at),
            ).fetchone()
        return self._document(row)

    def list_documents(self, project_id: str) -> list[DocumentRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at
                   FROM project_documents WHERE project_id = %s
                   ORDER BY created_at, document_id""",
                (UUID(project_id),),
            ).fetchall()
        return [self._document(row) for row in rows]

    def get_document(self, project_id: str, document_id: str) -> DocumentRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT document_id, project_id, uploader_id, filename, mime_type,
                          byte_size, checksum, storage_bucket, storage_key, created_at
                   FROM project_documents WHERE project_id = %s AND document_id = %s""",
                (UUID(project_id), UUID(document_id)),
            ).fetchone()
        return self._document(row) if row else None

    def delete_document(self, project_id: str, document_id: str) -> DocumentRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """DELETE FROM project_documents
                   WHERE project_id = %s AND document_id = %s
                   RETURNING document_id, project_id, uploader_id, filename, mime_type,
                             byte_size, checksum, storage_bucket, storage_key, created_at""",
                (UUID(project_id), UUID(document_id)),
            ).fetchone()
        return self._document(row) if row else None


class PostgresManualTextRepository(ManualTextRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def upsert(self, payload: ManualTextPayload, updated_by: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO manual_text
                (course_id, project_id, sprint_id, expectations_text, updated_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (course_id, project_id, sprint_id)
                DO UPDATE SET expectations_text = EXCLUDED.expectations_text,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = CURRENT_TIMESTAMP""",
                (UUID(payload.course_id), UUID(payload.project_id), payload.sprint_id,
                 " ".join(payload.expectations_text.split()), UUID(updated_by)),
            )

    def get(self, course_id: str, project_id: str, sprint_id: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT expectations_text FROM manual_text
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
        return row["expectations_text"] if row else None


def ensure_rubric_weights_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS rubric_weight_configs (
                course_id UUID PRIMARY KEY REFERENCES courses(course_id) ON DELETE CASCADE,
                weights JSONB NOT NULL,
                updated_by UUID NOT NULL REFERENCES users(user_id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


class PostgresRubricWeightsRepository(RubricWeightsRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_weights(self, course_id: str) -> RubricWeightsRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT course_id, weights, updated_by, updated_at
                FROM rubric_weight_configs WHERE course_id = %s""",
                (UUID(course_id),),
            ).fetchone()
        if not row:
            return None
        return RubricWeightsRecord(
            course_id=str(row["course_id"]),
            weights=row["weights"],
            updated_by=str(row["updated_by"]),
            updated_at=row["updated_at"],
        )

    def set_weights(self, course_id: str, weights: dict[str, float], updated_by: str) -> RubricWeightsRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO rubric_weight_configs (course_id, weights, updated_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (course_id)
                DO UPDATE SET weights = EXCLUDED.weights,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = CURRENT_TIMESTAMP
                RETURNING course_id, weights, updated_by, updated_at""",
                (UUID(course_id), Json(weights), UUID(updated_by)),
            ).fetchone()
        return RubricWeightsRecord(
            course_id=str(row["course_id"]),
            weights=row["weights"],
            updated_by=str(row["updated_by"]),
            updated_at=row["updated_at"],
        )


def ensure_instructor_model_selection_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS instructor_model_selections (
                user_id UUID PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                model_id VARCHAR(255) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )


def ensure_peer_evaluation_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS peer_evaluations (
                evaluation_id UUID PRIMARY KEY,
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                rater_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                rated_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                remarks TEXT,
                reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (rater_id, rated_id, project_id)
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_peer_eval_project "
            "ON peer_evaluations(project_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_peer_eval_rater "
            "ON peer_evaluations(rater_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_peer_eval_rated "
            "ON peer_evaluations(rated_id, created_at DESC)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS peer_evaluation_configs (
                course_id UUID PRIMARY KEY REFERENCES courses(course_id) ON DELETE CASCADE,
                is_open BOOLEAN NOT NULL DEFAULT FALSE,
                opens_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ,
                updated_by UUID NOT NULL REFERENCES users(user_id),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            "ALTER TABLE peer_evaluation_configs ADD COLUMN IF NOT EXISTS opens_at TIMESTAMPTZ"
        )
        connection.execute(
            "ALTER TABLE peer_evaluations ADD COLUMN IF NOT EXISTS reason TEXT"
        )


class PostgresPeerEvaluationRepository(PeerEvaluationRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _evaluation(row: dict) -> PeerEvaluationRecord:
        return PeerEvaluationRecord(
            evaluation_id=str(row["evaluation_id"]),
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            rater_id=str(row["rater_id"]),
            rated_id=str(row["rated_id"]),
            score=row["score"],
            remarks=row["remarks"],
            reason=row.get("reason"),
            created_at=row["created_at"],
        )

    def save_evaluation(self, evaluation: PeerEvaluationRecord) -> PeerEvaluationRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO peer_evaluations
                (evaluation_id, course_id, project_id, rater_id, rated_id, score, remarks, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (rater_id, rated_id, project_id)
                DO UPDATE SET score = EXCLUDED.score,
                              remarks = EXCLUDED.remarks,
                              reason = EXCLUDED.reason,
                              created_at = EXCLUDED.created_at
                RETURNING evaluation_id, course_id, project_id, rater_id, rated_id,
                          score, remarks, reason, created_at""",
                (
                    UUID(evaluation.evaluation_id),
                    UUID(evaluation.course_id),
                    UUID(evaluation.project_id),
                    UUID(evaluation.rater_id),
                    UUID(evaluation.rated_id),
                    evaluation.score,
                    evaluation.remarks,
                    evaluation.reason,
                    evaluation.created_at,
                ),
            ).fetchone()
        return self._evaluation(row)

    def get_evaluation(self, evaluation_id: str) -> PeerEvaluationRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM peer_evaluations WHERE evaluation_id = %s",
                (UUID(evaluation_id),),
            ).fetchone()
        return self._evaluation(row) if row else None

    def list_evaluations_by_rater(
        self, rater_id: str, project_id: str | None = None
    ) -> list[PeerEvaluationRecord]:
        if project_id:
            with self._pool.connection() as connection:
                db_rows = connection.execute(
                    """SELECT * FROM peer_evaluations
                    WHERE rater_id = %s AND project_id = %s
                    ORDER BY created_at DESC, evaluation_id DESC""",
                    (UUID(rater_id), UUID(project_id)),
                ).fetchall()
        else:
            with self._pool.connection() as connection:
                db_rows = connection.execute(
                    """SELECT * FROM peer_evaluations
                    WHERE rater_id = %s
                    ORDER BY created_at DESC, evaluation_id DESC""",
                    (UUID(rater_id),),
                ).fetchall()
        return [self._evaluation(row) for row in db_rows or []]

    def list_evaluations_by_project(
        self, project_id: str
    ) -> list[PeerEvaluationRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM peer_evaluations
                WHERE project_id = %s
                ORDER BY created_at DESC, evaluation_id DESC""",
                (UUID(project_id),),
            ).fetchall()
        return [self._evaluation(row) for row in rows or []]

    def list_evaluations_by_course(
        self, course_id: str
    ) -> list[PeerEvaluationRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM peer_evaluations
                WHERE course_id = %s
                ORDER BY created_at DESC, evaluation_id DESC""",
                (UUID(course_id),),
            ).fetchall()
        return [self._evaluation(row) for row in rows or []]

    def get_evaluation_by_rater_and_rated(
        self, rater_id: str, rated_id: str, project_id: str
    ) -> PeerEvaluationRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT * FROM peer_evaluations
                WHERE rater_id = %s AND rated_id = %s AND project_id = %s""",
                (UUID(rater_id), UUID(rated_id), UUID(project_id)),
            ).fetchone()
        return self._evaluation(row) if row else None

    def save_config(
        self, config: PeerEvaluationConfigRecord
    ) -> PeerEvaluationConfigRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO peer_evaluation_configs
                (course_id, is_open, opens_at, expires_at, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (course_id)
                DO UPDATE SET is_open = EXCLUDED.is_open,
                              opens_at = EXCLUDED.opens_at,
                              expires_at = EXCLUDED.expires_at,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = EXCLUDED.updated_at
                RETURNING course_id, is_open, opens_at, expires_at, updated_by, updated_at""",
                (
                    UUID(config.course_id),
                    config.is_open,
                    config.opens_at,
                    config.expires_at,
                    UUID(config.updated_by),
                    config.updated_at,
                ),
            ).fetchone()
        return self._config(row)

    def get_config(self, course_id: str) -> PeerEvaluationConfigRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM peer_evaluation_configs WHERE course_id = %s",
                (UUID(course_id),),
            ).fetchone()
        return self._config(row) if row else None

    @staticmethod
    def _config(row: dict) -> PeerEvaluationConfigRecord:
        return PeerEvaluationConfigRecord(
            course_id=str(row["course_id"]),
            is_open=row["is_open"],
            opens_at=row["opens_at"],
            expires_at=row["expires_at"],
            updated_by=str(row["updated_by"]),
            updated_at=row["updated_at"],
        )

    def delete_evaluation(self, evaluation_id: str) -> bool:
        """Delete an evaluation by ID. Returns True if deleted, False if not found."""
        with self._pool.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM peer_evaluations WHERE evaluation_id = %s",
                (UUID(evaluation_id),),
            )
        return cursor.rowcount > 0


class PostgresInstructorModelSelectionRepository(InstructorModelSelectionRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_selection(self, user_id: str) -> InstructorModelSelectionRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT user_id, model_id, updated_at
                FROM instructor_model_selections WHERE user_id = %s""",
                (UUID(user_id),),
            ).fetchone()
        if not row:
            return None
        return InstructorModelSelectionRecord(
            user_id=str(row["user_id"]),
            model_id=row["model_id"],
            updated_at=row["updated_at"],
        )

    def set_selection(self, user_id: str, model_id: str) -> InstructorModelSelectionRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO instructor_model_selections (user_id, model_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET model_id = EXCLUDED.model_id,
                              updated_at = CURRENT_TIMESTAMP
                RETURNING user_id, model_id, updated_at""",
                (UUID(user_id), model_id),
            ).fetchone()
        return InstructorModelSelectionRecord(
            user_id=str(row["user_id"]),
            model_id=row["model_id"],
            updated_at=row["updated_at"],
        )


def ensure_assessment_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS assessment_reports (
                report_id UUID PRIMARY KEY,
                model_name VARCHAR(255) NOT NULL,
                mode VARCHAR(255) NOT NULL,
                course_id UUID NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                sprint_id VARCHAR(100) NOT NULL,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                rubric_weights JSONB NOT NULL,
                team_score JSONB NOT NULL,
                individual_scores JSONB NOT NULL DEFAULT '[]'::jsonb,
                recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
                rubric_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
                strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
                weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb,
                override BOOLEAN NOT NULL DEFAULT FALSE,
                requirements_score NUMERIC(5, 2) CHECK (requirements_score BETWEEN 0 AND 100),
                code_quality_score NUMERIC(5, 2) CHECK (code_quality_score BETWEEN 0 AND 100),
                documentation_score NUMERIC(5, 2) CHECK (documentation_score BETWEEN 0 AND 100),
                collaboration_score NUMERIC(5, 2) CHECK (collaboration_score BETWEEN 0 AND 100),
                requirements_justification VARCHAR(500),
                code_quality_justification VARCHAR(500),
                documentation_justification VARCHAR(500),
                collaboration_justification VARCHAR(500),
                CONSTRAINT assessment_reports_manual_fields_check CHECK (
                    NOT override OR (
                        requirements_score IS NOT NULL AND
                        code_quality_score IS NOT NULL AND
                        documentation_score IS NOT NULL AND
                        collaboration_score IS NOT NULL AND
                        requirements_justification IS NOT NULL AND
                        code_quality_justification IS NOT NULL AND
                        documentation_justification IS NOT NULL AND
                        collaboration_justification IS NOT NULL
                    )
                )
            )"""
        )
        for statement in (
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS override BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS requirements_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS code_quality_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS documentation_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS collaboration_score NUMERIC(5, 2)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS requirements_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS code_quality_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS documentation_justification VARCHAR(500)",
            "ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS collaboration_justification VARCHAR(500)",
        ):
            connection.execute(statement)
        connection.execute(
            """DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'assessment_reports_manual_fields_check'
                ) THEN
                    ALTER TABLE assessment_reports
                    ADD CONSTRAINT assessment_reports_manual_fields_check CHECK (
                        NOT override OR (
                            requirements_score IS NOT NULL AND
                            code_quality_score IS NOT NULL AND
                            documentation_score IS NOT NULL AND
                            collaboration_score IS NOT NULL AND
                            requirements_justification IS NOT NULL AND
                            code_quality_justification IS NOT NULL AND
                            documentation_justification IS NOT NULL AND
                            collaboration_justification IS NOT NULL
                        )
                    );
                END IF;
            END $$"""
        )
        connection.execute("DROP TABLE IF EXISTS assessment_override")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_assessment_reports_course_project_sprint ON assessment_reports(course_id, project_id, sprint_id, generated_at DESC)")


class PostgresAssessmentRepository(AssessmentRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_report(self, report: AssessmentReport) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """INSERT INTO assessment_reports
                (report_id, model_name, mode, course_id, project_id,
                 sprint_id, generated_at, rubric_weights, team_score,
                 individual_scores, recommendations, rubric_scores,
                 strengths, weaknesses)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id)
                DO UPDATE SET model_name = EXCLUDED.model_name,
                              mode = EXCLUDED.mode,
                              course_id = EXCLUDED.course_id,
                              project_id = EXCLUDED.project_id,
                              sprint_id = EXCLUDED.sprint_id,
                              generated_at = EXCLUDED.generated_at,
                              rubric_weights = EXCLUDED.rubric_weights,
                              team_score = EXCLUDED.team_score,
                              individual_scores = EXCLUDED.individual_scores,
                              recommendations = EXCLUDED.recommendations,
                              rubric_scores = EXCLUDED.rubric_scores,
                              strengths = EXCLUDED.strengths,
                              weaknesses = EXCLUDED.weaknesses""",
                (
                    UUID(report.report_id.replace('rpt-', '')) if report.report_id.startswith('rpt-') else UUID(report.report_id),
                    report.model_name,
                    report.mode,
                    UUID(report.course_id),
                    UUID(report.project_id),
                    report.sprint_id,
                    report.generated_at,
                    Json(report.rubric_weights),
                    Json(report.team_score.model_dump(mode='json')),
                    Json([score.model_dump(mode='json') for score in report.individual_scores]),
                    Json(report.recommendations),
                    Json({k: v.model_dump(mode='json') for k, v in report.rubric_scores.items()}),
                    Json(report.strengths),
                    Json(report.weaknesses),
                ),
            )

    def get_report(self, report_id: str) -> AssessmentReport | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM assessment_reports WHERE report_id = %s",
                (UUID(report_id),),
            ).fetchone()
            return self._report(row) if row else None

    def update_manual_assessment(self, report_id: str, patch: dict[str, object]) -> AssessmentReport | None:
        columns = {
            "requirements_score": "requirements_score",
            "code_quality_score": "code_quality_score",
            "documentation_score": "documentation_score",
            "collaboration_score": "collaboration_score",
            "requirements_justification": "requirements_justification",
            "code_quality_justification": "code_quality_justification",
            "documentation_justification": "documentation_justification",
            "collaboration_justification": "collaboration_justification",
            "rubric_weights": "rubric_weights",
            "team_score": "team_score",
            "individual_scores": "individual_scores",
            "rubric_scores": "rubric_scores",
            "strengths": "strengths",
            "weaknesses": "weaknesses",
            "recommendations": "recommendations",
        }
        json_columns = {
            "rubric_weights",
            "team_score",
            "individual_scores",
            "rubric_scores",
            "strengths",
            "weaknesses",
            "recommendations",
        }
        assignments = ["override = TRUE"]
        values = []
        for key, value in patch.items():
            column = columns.get(key)
            if column is None:
                continue
            assignments.append(f"{column} = %s")
            values.append(Json(value) if column in json_columns else value)

        with self._pool.connection() as connection:
            row = connection.execute(
                f"UPDATE assessment_reports SET {', '.join(assignments)} "
                "WHERE report_id = %s RETURNING *",
                (*values, UUID(report_id.replace("rpt-", ""))),
            ).fetchone()
        return self._report(row) if row else None

    def list_reports(self, course_id: str, project_id: str, sprint_id: str) -> list[AssessmentReport]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s
                ORDER BY generated_at DESC""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchall()
        return [self._report(row) for row in rows or []]

    def list_project_reports(self, course_id: str, project_id: str) -> list[AssessmentReport]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s
                ORDER BY generated_at DESC""",
                (UUID(course_id), UUID(project_id)),
            ).fetchall()
        return [self._report(row) for row in rows or []]

    def get_latest_report(self, course_id: str, project_id: str, sprint_id: str) -> AssessmentReport | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT * FROM assessment_reports
                WHERE course_id = %s AND project_id = %s AND sprint_id = %s
                ORDER BY generated_at DESC LIMIT 1""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            return self._report(row) if row else None

    @staticmethod
    def _report(row: dict) -> AssessmentReport:
        from app.schemas.assessment import RubricDimensionScoreDetail, StudentScore, TeamScore
        rubric_scores = {}
        if row.get("rubric_scores"):
            for key, value in row["rubric_scores"].items():
                rubric_scores[key] = RubricDimensionScoreDetail.model_validate(value)

        return AssessmentReport(
            report_id=str(row["report_id"]),
            model_name=row["model_name"],
            mode=row["mode"],
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"],
            generated_at=row["generated_at"],
            rubric_weights=row["rubric_weights"],
            team_score=TeamScore.model_validate(row["team_score"]),
            individual_scores=[StudentScore.model_validate(x) for x in row["individual_scores"]],
            recommendations=row["recommendations"],
            rubric_scores=rubric_scores,
            strengths=row["strengths"],
            weaknesses=row["weaknesses"],
            override=row.get("override", False),
            requirements_score=float(row["requirements_score"]) if row.get("requirements_score") is not None else None,
            code_quality_score=float(row["code_quality_score"]) if row.get("code_quality_score") is not None else None,
            documentation_score=float(row["documentation_score"]) if row.get("documentation_score") is not None else None,
            collaboration_score=float(row["collaboration_score"]) if row.get("collaboration_score") is not None else None,
            requirements_justification=row.get("requirements_justification"),
            code_quality_justification=row.get("code_quality_justification"),
            documentation_justification=row.get("documentation_justification"),
            collaboration_justification=row.get("collaboration_justification"),
        )


class PostgresMetricsRepository(MetricsRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def save_metrics(self, metrics: IngestionMetricBundle) -> None:
        with self._pool.connection() as connection:
            with connection.transaction():
                connection.execute(
                    "DELETE FROM ingestion_runs WHERE project_id = %s AND sprint_id = %s",
                    (UUID(metrics.project_id), metrics.sprint_id),
                )
                head_sha = metrics.commits[0].sha if metrics.commits else None
                run = connection.execute(
                    """INSERT INTO ingestion_runs
                    (course_id, project_id, sprint_id, local_repo_path, head_sha,
                     commit_frequency, code_churn, pr_turnaround_hours,
                     assigned_story_points, completion_percent, captured_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING ingestion_run_id""",
                    (UUID(metrics.course_id), UUID(metrics.project_id), metrics.sprint_id,
                     metrics.local_repo_path, metrics.head_sha, metrics.commit_frequency, metrics.code_churn,
                     metrics.pr_turnaround_hours, metrics.assigned_story_points,
                     metrics.completion_percent, metrics.captured_at),
                ).fetchone()
                for commit in metrics.commits:
                    connection.execute(
                        """INSERT INTO ingestion_commits
                        (ingestion_run_id, sha, author, author_email, student_id, message, timestamp,
                         lines_added, lines_deleted, files_changed)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (run["ingestion_run_id"], commit.sha, commit.author, commit.author_email, commit.student_id, commit.message,
                         commit.timestamp, commit.lines_added, commit.lines_deleted,
                         Json([file.model_dump() for file in commit.files_changed])),
                    )

    def get_metrics(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> IngestionMetricBundle | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT ir.course_id, ir.project_id, ir.sprint_id,
                    ir.local_repo_path, ir.head_sha,
                    ir.commit_frequency, ir.code_churn, ir.pr_turnaround_hours,
                    ir.assigned_story_points, ir.completion_percent, ir.captured_at
                    FROM ingestion_runs ir
                    WHERE ir.course_id = %s AND ir.project_id = %s AND ir.sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            if not row:
                return None
            commit_filters = [
                "ingestion_run_id = (SELECT ingestion_run_id FROM ingestion_runs "
                "WHERE course_id = %s AND project_id = %s AND sprint_id = %s)"
            ]
            commit_params: list[object] = [UUID(course_id), UUID(project_id), sprint_id]
            if start_datetime is not None:
                commit_filters.append("timestamp >= %s")
                commit_params.append(start_datetime)
            if end_datetime is not None:
                commit_filters.append("timestamp < %s")
                commit_params.append(end_datetime)
            commit_rows = connection.execute(
                """SELECT sha, author, author_email, student_id, message, timestamp, lines_added,
                    lines_deleted, files_changed
                    FROM ingestion_commits WHERE """
                + " AND ".join(commit_filters)
                + " ORDER BY timestamp, sha",
                commit_params,
            ).fetchall()
        from app.schemas.assessment import CommitInfo
        return IngestionMetricBundle(
            course_id=str(row["course_id"]), project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"], commit_frequency=row["commit_frequency"],
            code_churn=row["code_churn"], pr_turnaround_hours=row["pr_turnaround_hours"],
            assigned_story_points=row["assigned_story_points"],
            completion_percent=row["completion_percent"],
            commits=[
                CommitInfo(
                    **{
                        **dict(commit),
                        "student_id": str(commit["student_id"]) if commit["student_id"] else None,
                        "files_changed": commit["files_changed"],
                    }
                )
                for commit in commit_rows
            ],
            local_repo_path=row["local_repo_path"],
            head_sha=row["head_sha"],
            captured_at=row["captured_at"],
        )

    def get_metrics_page(
        self,
        course_id: str,
        project_id: str,
        sprint_id: str,
        limit: int,
        offset: int,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> tuple[IngestionMetricBundle | None, int]:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT ir.course_id, ir.project_id, ir.sprint_id,
                    ir.local_repo_path, ir.head_sha, ir.commit_frequency,
                    ir.code_churn, ir.pr_turnaround_hours,
                    ir.assigned_story_points, ir.completion_percent, ir.captured_at,
                    ir.ingestion_run_id
                    FROM ingestion_runs ir
                    WHERE ir.course_id = %s AND ir.project_id = %s AND ir.sprint_id = %s""",
                (UUID(course_id), UUID(project_id), sprint_id),
            ).fetchone()
            if not row:
                return None, 0
            commit_filters = ["ingestion_run_id = %s"]
            commit_params: list[object] = [row["ingestion_run_id"]]
            if start_datetime is not None:
                commit_filters.append("timestamp >= %s")
                commit_params.append(start_datetime)
            if end_datetime is not None:
                commit_filters.append("timestamp < %s")
                commit_params.append(end_datetime)
            total = connection.execute(
                "SELECT COUNT(*) AS total FROM ingestion_commits WHERE "
                + " AND ".join(commit_filters),
                commit_params,
            ).fetchone()["total"]
            commit_rows = connection.execute(
                """SELECT sha, author, author_email, student_id, message, timestamp, lines_added,
                    lines_deleted, files_changed
                    FROM ingestion_commits
                    WHERE """
                + " AND ".join(commit_filters)
                + " ORDER BY timestamp, sha LIMIT %s OFFSET %s",
                [*commit_params, limit, offset],
            ).fetchall()
        from app.schemas.assessment import CommitInfo
        return IngestionMetricBundle(
            course_id=str(row["course_id"]), project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"], commit_frequency=row["commit_frequency"],
            code_churn=row["code_churn"], pr_turnaround_hours=row["pr_turnaround_hours"],
            assigned_story_points=row["assigned_story_points"],
            completion_percent=row["completion_percent"],
            commits=[
                CommitInfo(
                    **{
                        **dict(commit),
                        "student_id": str(commit["student_id"]) if commit["student_id"] else None,
                        "files_changed": commit["files_changed"],
                    }
                )
                for commit in commit_rows
            ],
            local_repo_path=row["local_repo_path"], head_sha=row["head_sha"],
            captured_at=row["captured_at"],
        ), total


class PostgresJiraIngestionRunRepository(JiraIngestionRunRepository):
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @staticmethod
    def _run(row: dict) -> JiraIngestionRunRecord:
        snapshot = row.get("cleaned_snapshot")
        return JiraIngestionRunRecord(
            id=str(row["run_id"]),
            course_id=str(row["course_id"]),
            project_id=str(row["project_id"]),
            sprint_id=row["sprint_id"],
            jira_project_key=row["jira_project_key"],
            jql=row["jql"],
            raw_bucket=row["raw_bucket"],
            raw_object_key=row["raw_object_key"],
            issue_count=row["issue_count"],
            captured_at=row["captured_at"],
            processed_at=row["processed_at"],
            processing_status=row["processing_status"],
            normalization_version=row["normalization_version"],
            processing_error=row["processing_error"],
            cleaned_snapshot=JiraCleanedSnapshot.model_validate(snapshot) if snapshot else None,
        )

    def create_run(self, run: JiraIngestionRunRecord) -> JiraIngestionRunRecord:
        with self._pool.connection() as connection:
            row = connection.execute(
                """INSERT INTO jira_ingestion_runs
                (run_id, course_id, project_id, sprint_id, jira_project_key, jql,
                 raw_bucket, raw_object_key, issue_count, captured_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *""",
                (UUID(run.id), UUID(run.course_id), UUID(run.project_id), run.sprint_id,
                 run.jira_project_key, run.jql, run.raw_bucket, run.raw_object_key,
                 run.issue_count, run.captured_at),
            ).fetchone()
        return self._run(row)

    def get_run(self, project_id: str, sprint_id: str, run_id: str) -> JiraIngestionRunRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s AND sprint_id = %s AND run_id = %s",
                (UUID(project_id), sprint_id, UUID(run_id)),
            ).fetchone()
        return self._run(row) if row else None

    def list_project_runs(self, project_id: str) -> list[JiraIngestionRunRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s ORDER BY captured_at DESC, run_id DESC",
                (UUID(project_id),),
            ).fetchall()
        return [self._run(row) for row in rows]

    def list_runs(self, project_id: str, sprint_id: str) -> list[JiraIngestionRunRecord]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jira_ingestion_runs WHERE project_id = %s AND sprint_id = %s ORDER BY captured_at DESC, run_id DESC",
                (UUID(project_id), sprint_id),
            ).fetchall()
        return [self._run(row) for row in rows]

    def update_processed_run(self, project_id: str, sprint_id: str, run_id: str, status: str, processed_at: datetime | None, normalization_version: str | None, processing_error: str | None, cleaned_snapshot: JiraCleanedSnapshot | None) -> JiraIngestionRunRecord | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """UPDATE jira_ingestion_runs SET processing_status = %s,
                processed_at = %s, normalization_version = %s, processing_error = %s,
                cleaned_snapshot = %s
                WHERE project_id = %s AND sprint_id = %s AND run_id = %s
                RETURNING *""",
                (status, processed_at, normalization_version, processing_error,
                 Json(cleaned_snapshot.model_dump(mode="json")) if cleaned_snapshot else None,
                 UUID(project_id), sprint_id, UUID(run_id)),
            ).fetchone()
        return self._run(row) if row else None


def create_user_pool(connection_string: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=connection_string,
        kwargs={"row_factory": dict_row},
        min_size=1,
        max_size=5,
        open=False,
    )