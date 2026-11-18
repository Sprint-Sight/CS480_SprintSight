from app.repositories.insights import (
    InMemoryInsightsRepository, InsightsRepository, PostgresInsightsRepository,
)

def _methods(cls):
    return {n for n in dir(cls) if not n.startswith("_") and callable(getattr(cls, n))}

def test_both_repositories_implement_the_protocol():
    required = {n for n in vars(InsightsRepository) if not n.startswith("_")}
    for impl in (InMemoryInsightsRepository, PostgresInsightsRepository):
        assert not required - _methods(impl), f"{impl.__name__} is missing {required - _methods(impl)}"