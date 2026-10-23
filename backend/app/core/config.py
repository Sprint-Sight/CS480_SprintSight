from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = Field(default="SprintSight API", alias="PROJECT_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(alias="SECRET_KEY")
    access_token_expire_minutes: int = 120
    jwt_algorithm: str = "HS256"

    postgres_server: str = Field(default="db", alias="POSTGRES_SERVER")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="sprintsight", alias="POSTGRES_DB")
    database_url: str = Field(default="", alias="DATABASE_URL")

    github_pat_token: str = Field(default="", alias="GITHUB_PAT_TOKEN")
    local_repository_root: Path = Field(default=Path("repo"), alias="LOCAL_REPOSITORY_ROOT")
    credentials_encryption_key: str = Field(default="", alias="CREDENTIALS_ENCRYPTION_KEY")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")
    jira_email: str = Field(default="", alias="JIRA_EMAIL")
    jira_domain: str = Field(default="", alias="JIRA_DOMAIN")
    jira_timeout_seconds: float = Field(default=30, alias="JIRA_TIMEOUT_SECONDS")
    jira_story_points_field: str = Field(default="customfield_10016", alias="JIRA_STORY_POINTS_FIELD")
    jira_sprint_field: str = Field(default="customfield_10020", alias="JIRA_SPRINT_FIELD")
    minio_bucket_raw: str = Field(default="raw-jira-data", alias="MINIO_BUCKET_RAW")
    minio_bucket_documents: str = Field(default="project-documents", alias="MINIO_BUCKET_DOCUMENTS")
    document_max_file_size: int = Field(default=25 * 1024 * 1024, alias="DOCUMENT_MAX_FILE_SIZE")
    document_max_request_size: int = Field(default=100 * 1024 * 1024, alias="DOCUMENT_MAX_REQUEST_SIZE")

    bootstrap_admin_email: str = Field(default="", alias="BOOTSTRAP_ADMIN_EMAIL")
    bootstrap_admin_password: str = Field(default="", alias="BOOTSTRAP_ADMIN_PASSWORD")
    bootstrap_admin_name: str = Field(default="System Admin", alias="BOOTSTRAP_ADMIN_NAME")
    bootstrap_instructor_email: str = Field(default="", alias="BOOTSTRAP_INSTRUCTOR_EMAIL")
    bootstrap_instructor_password: str = Field(default="", alias="BOOTSTRAP_INSTRUCTOR_PASSWORD")
    bootstrap_instructor_name: str = Field(default="Sample Instructor", alias="BOOTSTRAP_INSTRUCTOR_NAME")
    bootstrap_student_email: str = Field(default="", alias="BOOTSTRAP_STUDENT_EMAIL")
    bootstrap_student_password: str = Field(default="", alias="BOOTSTRAP_STUDENT_PASSWORD")
    bootstrap_student_name: str = Field(default="Sample Student", alias="BOOTSTRAP_STUDENT_NAME")

    email_smtp_host: str = Field(default="", alias="EMAIL_SMTP_HOST")
    email_smtp_port: int = Field(default=587, alias="EMAIL_SMTP_PORT", ge=1, le=65535)
    email_smtp_username: str = Field(default="", alias="EMAIL_SMTP_USERNAME")
    email_smtp_password: str = Field(default="", alias="EMAIL_SMTP_PASSWORD")
    email_from_address: str = Field(default="", alias="EMAIL_FROM_ADDRESS")
    email_from_name: str = Field(default="SprintSight", alias="EMAIL_FROM_NAME")
    email_smtp_use_tls: bool = Field(default=True, alias="EMAIL_SMTP_USE_TLS")
    email_smtp_use_ssl: bool = Field(default=False, alias="EMAIL_SMTP_USE_SSL")
    email_transport: str = Field(default="smtp", alias="EMAIL_TRANSPORT")
    email_outbox_path: Path = Field(default=Path("logs/email-outbox"), alias="EMAIL_OUTBOX_PATH")
    email_daily_send_cap: int = Field(default=450, alias="EMAIL_DAILY_SEND_CAP", ge=0)
    email_send_interval_seconds: float = Field(
        default=1.0, alias="EMAIL_SEND_INTERVAL_SECONDS", ge=0.0, le=60.0,
    )
    email_dispatch_interval_seconds: float = Field(
        default=5.0, alias="EMAIL_DISPATCH_INTERVAL_SECONDS", ge=0.5, le=300.0,
    )
    email_smtp_max_attempts: int = Field(default=3, alias="EMAIL_SMTP_MAX_ATTEMPTS", ge=1, le=10)
    email_smtp_retry_backoff_seconds: float = Field(
        default=2.0, alias="EMAIL_SMTP_RETRY_BACKOFF_SECONDS", ge=0.0, le=60.0,
    )
    email_smtp_circuit_breaker_seconds: int = Field(
        default=300, alias="EMAIL_SMTP_CIRCUIT_BREAKER_SECONDS", ge=0, le=86400,
    )
    email_quota_backoff_seconds: int = Field(
        default=1800, alias="EMAIL_QUOTA_BACKOFF_SECONDS", ge=0, le=86400,
    )
    email_queue_max_attempts: int = Field(
        default=5, alias="EMAIL_QUEUE_MAX_ATTEMPTS", ge=1, le=100,
    )
    email_frontend_base_url: str = Field(
        default="http://localhost:3000", alias="EMAIL_FRONTEND_BASE_URL",
    )
    email_first_time_token_expire_minutes: int = Field(
        default=1440, alias="EMAIL_FIRST_TIME_TOKEN_EXPIRE_MINUTES", ge=1, le=10080,
    )
    email_password_reset_token_expire_minutes: int = Field(
        default=30, alias="EMAIL_PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", ge=1, le=1440,
    )

    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    assessment_mode: str = Field(default="mock", alias="ASSESSMENT_MODE")
    default_model_name: str = Field(default="mock-rubric-v1", alias="DEFAULT_MODEL_NAME")
    ai_engine_url: str = Field(default="http://host.docker.internal:8001", alias="AI_ENGINE_URL")
    ai_engine_timeout_seconds: float = Field(default=600.0, alias="AI_ENGINE_TIMEOUT_SECONDS")

    audit_log_path: str = Field(default="logs/audit.log", alias="AUDIT_LOG_PATH")
    audit_hot_retention_days: int = Field(default=168, alias="AUDIT_HOT_RETENTION_DAYS", ge=1)
    audit_action_archive_retention_days: int = Field(default=365, alias="AUDIT_ACTION_ARCHIVE_RETENTION_DAYS", ge=1)
    audit_override_archive_retention_days: int = Field(default=365, alias="AUDIT_OVERRIDE_ARCHIVE_RETENTION_DAYS", ge=1)
    audit_archive_batch_size: int = Field(default=500, alias="AUDIT_ARCHIVE_BATCH_SIZE", ge=1, le=10000)
    minio_bucket_audit_archive: str = Field(default="audit-archive", alias="MINIO_BUCKET_AUDIT_ARCHIVE")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    minio_endpoint_url: str = Field(default="http://minio:9000", alias="MINIO_ENDPOINT_URL")
    minio_access_key: str = Field(alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(alias="MINIO_SECRET_KEY")

    def database_connection_string(self) -> str:
        if self.database_url:
            return (
                self.database_url.replace("postgresql+asyncpg://", "postgresql://")
                .replace("postgresql+psycopg2://", "postgresql://")
            )
        return (
            f"host={self.postgres_server} port=5432 dbname={self.postgres_db} "
            f"user={self.postgres_user} password={self.postgres_password}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
