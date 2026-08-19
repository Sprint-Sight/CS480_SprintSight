from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = Field(default="SprintSight API", alias="PROJECT_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default="dev-only-secret-key-change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = 120
    jwt_algorithm: str = "HS256"

    postgres_server: str = Field(default="localhost", alias="POSTGRES_SERVER")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="sprintsight", alias="POSTGRES_DB")

    github_pat_token: str = Field(default="", alias="GITHUB_PAT_TOKEN")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")
    jira_domain: str = Field(default="", alias="JIRA_DOMAIN")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
