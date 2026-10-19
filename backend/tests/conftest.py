import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("CREDENTIALS_ENCRYPTION_KEY", "")
os.environ.setdefault("POSTGRES_PASSWORD", "test-only-database-password")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-only-minio-access")
os.environ.setdefault("MINIO_SECRET_KEY", "test-only-minio-secret")

from app.dependencies.auth import (
    get_action_audit_repository,
    get_assessment_repository,
    get_audit_repository,
    get_audit_retention_config_repository,
    get_document_repository,
    get_manual_text_repository,
    get_notification_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.in_memory import (
    InMemoryActionAuditRepository,
    InMemoryAssessmentRepository,
    InMemoryAuditRepository,
    InMemoryAuditRetentionConfigRepository,
    InMemoryDocumentRepository,
    InMemoryManualTextRepository,
    InMemoryNotificationRepository,
    InMemoryProjectRepository,
    InMemoryUserRepository,
)


@pytest.fixture(autouse=True)
def override_user_repository():
    repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    document_repository = InMemoryDocumentRepository()
    manual_text_repository = InMemoryManualTextRepository()
    assessment_repository = InMemoryAssessmentRepository()
    audit_repository = InMemoryAuditRepository()
    action_audit_repository = InMemoryActionAuditRepository()
    notification_repository = InMemoryNotificationRepository()
    audit_retention_config_repository = InMemoryAuditRetentionConfigRepository()
    app.dependency_overrides[get_user_repository] = lambda: repository
    from app.dependencies.auth import get_project_repository
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_document_repository] = lambda: document_repository
    app.dependency_overrides[get_manual_text_repository] = lambda: manual_text_repository
    app.dependency_overrides[get_assessment_repository] = lambda: assessment_repository
    app.dependency_overrides[get_audit_repository] = lambda: audit_repository
    app.dependency_overrides[get_action_audit_repository] = lambda: action_audit_repository
    app.dependency_overrides[get_notification_repository] = lambda: notification_repository
    app.dependency_overrides[get_audit_retention_config_repository] = lambda: audit_retention_config_repository
    yield project_repository
    app.dependency_overrides.pop(get_user_repository, None)
    app.dependency_overrides.pop(get_project_repository, None)
    app.dependency_overrides.pop(get_document_repository, None)
    app.dependency_overrides.pop(get_manual_text_repository, None)
    app.dependency_overrides.pop(get_assessment_repository, None)
    app.dependency_overrides.pop(get_audit_repository, None)
    app.dependency_overrides.pop(get_action_audit_repository, None)
    app.dependency_overrides.pop(get_notification_repository, None)
    app.dependency_overrides.pop(get_audit_retention_config_repository, None)
