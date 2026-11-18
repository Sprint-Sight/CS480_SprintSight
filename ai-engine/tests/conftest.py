import pytest


@pytest.fixture(autouse=True)
def no_ollama_context_lookup(monkeypatch):
    """The grounding judge asks the Ollama server what context it will really give the judge
    model. Tests must never reach for a real server (or wait on a DNS lookup of 'ollama'), so by
    default the answer is 'unknown' and the configured MODEL_NUM_CTX is used. Tests of the lookup
    itself import the real function at module level, before this patch applies."""
    from evaluation.judges import citation_grounding as judge

    async def unknown(model: str) -> None:
        return None

    monkeypatch.setattr(judge, "_server_context_limit", unknown)
    judge._server_context.clear()

"""
MLflow's default local file store is a subdir of the current working directory, which
pytest changes to a temp dir. This fixture sets MLflow's local file store to a temp dir
outside the pytest temp dir, so that MLflow's SQLite database is not deleted between tests.
"""
@pytest.fixture(scope='session', autouse=True)
def _isolated_mlflow(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    mlflow_dir = tmp_path_factory.mktemp('mlflow')
    patch.setenv('MLFLOW_TRACKING_URI', f"sqlite:///{mlflow_dir / 'mlflow.db'}")
    # A SQLite store keeps only metadata in the database. Artifacts go to ./mlruns, which is the
    # real folder in ai-engine/ (with the user's own runs in it) unless the root is set. MLflow
    # reads this variable for exactly that; it is private to MLflow, so a test below fails if an
    # upgrade stops honouring it.
    patch.setenv('_MLFLOW_SERVER_ARTIFACT_ROOT', str(mlflow_dir / 'artifacts'))
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def fresh_prompt_registry_cache():
    """The prompt registry remembers what it found in a tracking store; a test's fake or temporary
    store must not be answered from another test's cache."""
    from llmops.prompt_registry import clear_prompt_cache

    clear_prompt_cache()
    yield
    clear_prompt_cache()