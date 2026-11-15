"""model_digest reads Ollama's /api/tags (the digest is not in /api/show)."""

import httpx
import pytest

from evaluation.offline import provenance

DIGEST = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
OTHER = "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
TAGS = {"models": [
    {"name": "sprintsight-qwen:latest", "digest": OTHER},
    {"name": "sprintsight-mistral:latest", "digest": DIGEST},
    {"name": "mistral:7b-q4", "digest": OTHER},
]}


@pytest.fixture
def ollama(monkeypatch):
    """Route provenance's httpx calls through a handler; returns the list of paths requested."""
    seen: list[str] = []

    def install(handler):
        def respond(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            return handler(request)

        monkeypatch.setattr(
            provenance.httpx, "get",
            lambda url, **kw: httpx.Client(transport=httpx.MockTransport(respond)).get(url, **kw),
        )
        return seen

    return install


def _tags(request):
    return httpx.Response(200, json=TAGS)


def test_untagged_name_matches_latest_and_drops_the_prefix(ollama) -> None:
    seen = ollama(_tags)

    assert provenance.model_digest("sprintsight-mistral") == "0123456789abcdef"
    assert seen == ["/api/tags"]


def test_explicit_tag_must_match_exactly(ollama) -> None:
    ollama(_tags)

    assert provenance.model_digest("mistral:7b-q4") == "fedcba9876543210"
    assert provenance.model_digest("mistral:latest") is None


def test_unknown_model_is_none(ollama) -> None:
    ollama(_tags)

    assert provenance.model_digest("nope") is None


def test_server_error_is_none(ollama) -> None:
    ollama(lambda request: httpx.Response(500))

    assert provenance.model_digest("sprintsight-mistral") is None


def test_unreachable_server_is_none(ollama) -> None:
    def refuse(request):
        raise httpx.ConnectError("refused")

    ollama(refuse)

    assert provenance.model_digest("sprintsight-mistral") is None
