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

    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    assessment_mode: str = Field(default="mock", alias="ASSESSMENT_MODE")
    default_model_name: str = Field(default="mock-rubric-v1", alias="DEFAULT_MODEL_NAME")

    audit_log_path: str = Field(default="logs/audit.log", alias="AUDIT_LOG_PATH")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    minio_endpoint_url: str = "http://minio:9000"
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
