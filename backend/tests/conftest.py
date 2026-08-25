import pytest
import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("POSTGRES_PASSWORD", "test-only-database-password")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-only-minio-access")
os.environ.setdefault("MINIO_SECRET_KEY", "test-only-minio-secret")

from app.dependencies.auth import get_user_repository
from app.main import app
from app.repositories.in_memory import InMemoryProjectRepository, InMemoryUserRepository


@pytest.fixture(autouse=True)
def override_user_repository():
    repository = InMemoryUserRepository()
    project_repository = InMemoryProjectRepository()
    app.dependency_overrides[get_user_repository] = lambda: repository
    from app.dependencies.auth import get_project_repository
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    yield
    app.dependency_overrides.pop(get_user_repository, None)
    app.dependency_overrides.pop(get_project_repository, None)
