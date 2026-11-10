import pytest


@pytest.fixture(autouse=True)
def no_ollama_context_lookup(monkeypatch):
    """The grounding judge asks the Ollama server what context it will really give the judge
    model. Tests must never reach for a real server (or wait on a DNS lookup of 'ollama'), so by
    default the answer is 'unknown' and the configured MODEL_NUM_CTX is used. Tests of the lookup
    itself import the real function at module level, before this patch applies."""
    from judges import citation_ground_custom_judge as judge

    async def unknown(model: str) -> None:
        return None

    monkeypatch.setattr(judge, "_server_context_limit", unknown)
    judge._server_context.clear()
