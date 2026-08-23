import pytest

from app.dependencies.auth import get_user_repository
from app.main import app
from app.repositories.in_memory import InMemoryUserRepository


@pytest.fixture(autouse=True)
def override_user_repository():
    repository = InMemoryUserRepository()
    app.dependency_overrides[get_user_repository] = lambda: repository
    yield
    app.dependency_overrides.pop(get_user_repository, None)
