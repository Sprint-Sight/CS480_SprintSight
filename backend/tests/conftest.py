import pytest

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
