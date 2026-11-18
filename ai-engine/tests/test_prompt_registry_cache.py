"""A prompt that is already registered is not looked up again on every assessment."""

from types import SimpleNamespace
from typing import cast

from mlflow import MlflowClient

from llmops.prompt_registry import _is_prompt_registered, _register_dimension_prompt


class FakeRegistry:
    """The MlflowClient calls the lookup makes, counted. Each version is one request."""

    def __init__(self, templates: dict[str, str], tracking_uri: str = "sqlite:///a.db") -> None:
        self.tracking_uri = tracking_uri
        self.versions = {name: {1: template} for name, template in templates.items()}
        self.calls = 0

    def get_prompt(self, name):
        self.calls += 1
        return SimpleNamespace(name=name) if name in self.versions else None

    def search_prompt_versions(self, name):
        self.calls += 1
        return [SimpleNamespace(version=v) for v in self.versions[name]]

    def get_prompt_version(self, name, version):
        self.calls += 1
        return SimpleNamespace(name=name, version=version, template=self.versions[name][version])


def as_client(registry: FakeRegistry) -> MlflowClient:
    return cast(MlflowClient, registry)


def test_a_registered_prompt_is_looked_up_once_not_on_every_assessment() -> None:
    registry = FakeRegistry({"Evaluate_testing": "grade testing"})

    first = _is_prompt_registered("Evaluate_testing", "grade testing", as_client(registry))
    calls_for_first_lookup = registry.calls
    second = _is_prompt_registered("Evaluate_testing", "grade testing", as_client(registry))
    third = _is_prompt_registered("Evaluate_testing", "grade testing", as_client(registry))

    assert first is not None and second is first and third is first
    assert calls_for_first_lookup > 0
    assert registry.calls == calls_for_first_lookup  # the repeats cost nothing


def test_a_prompt_that_is_not_registered_is_looked_up_again_so_a_new_one_is_found() -> None:
    registry = FakeRegistry({"Evaluate_testing": "old template"})
    assert _is_prompt_registered("Evaluate_testing", "new template", as_client(registry)) is None

    registry.versions["Evaluate_testing"][2] = "new template"  # someone registers it meanwhile

    found = _is_prompt_registered("Evaluate_testing", "new template", as_client(registry))
    assert found is not None and found.version == 2


def test_the_cache_does_not_mix_up_tracking_stores_or_templates() -> None:
    store_a = FakeRegistry({"Evaluate_testing": "grade testing"}, "sqlite:///a.db")
    store_b = FakeRegistry({"Evaluate_testing": "something else"}, "sqlite:///b.db")
    assert _is_prompt_registered("Evaluate_testing", "grade testing", as_client(store_a)) is not None

    assert _is_prompt_registered("Evaluate_testing", "grade testing", as_client(store_b)) is None
    assert _is_prompt_registered("Evaluate_testing", "different template", as_client(store_a)) is None


def test_registering_dimension_prompts_twice_reports_the_same_versions_without_rereading() -> None:
    registry = FakeRegistry({"Evaluate_testing": "grade testing"})
    first: dict[str, str] = {}
    second: dict[str, str] = {}

    _register_dimension_prompt("Evaluate_testing", "grade testing", {}, first, as_client(registry))
    calls = registry.calls
    _register_dimension_prompt("Evaluate_testing", "grade testing", {}, second, as_client(registry))

    assert first == second == {"Evaluate_testing": 1}
    assert registry.calls == calls
