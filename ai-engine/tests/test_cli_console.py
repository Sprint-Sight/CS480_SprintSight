"""Every command-line entry point puts stdout and stderr in UTF-8, through one helper."""

import importlib
import sys

import pytest

from llmops.console import use_utf8_streams


class FakeStream:
    def __init__(self) -> None:
        self.reconfigured: list[dict] = []

    def reconfigure(self, **kwargs) -> None:
        self.reconfigured.append(kwargs)


def test_stdout_and_stderr_are_switched_to_utf8_and_a_plain_stream_is_left_alone(monkeypatch) -> None:
    out, err = FakeStream(), FakeStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    use_utf8_streams()

    expected = [{"encoding": "utf-8", "errors": "replace"}]
    assert out.reconfigured == expected and err.reconfigured == expected

    class NoReconfigure:  # a captured or redirected stream has no reconfigure()
        pass

    monkeypatch.setattr(sys, "stdout", NoReconfigure())
    use_utf8_streams()  # must not raise


@pytest.mark.parametrize(
    ("module", "takes_argv"),
    [
        ("evaluation.offline.cli", True),
        ("evaluation.offline.judge_study.cli", True),
        ("research.trials.validation_harness", False),
        ("research.trials.run_fixture_trial", False),
        ("research.trials.run_cs203_trial", False),
    ],
)
def test_each_entry_point_sets_up_utf8_before_it_parses_arguments(monkeypatch, module, takes_argv) -> None:
    imported = importlib.import_module(module)
    calls: list[str] = []
    monkeypatch.setattr(imported, "use_utf8_streams", lambda: calls.append(module))
    monkeypatch.setattr(sys, "argv", ["prog", "--help"])

    with pytest.raises(SystemExit):
        if takes_argv:
            imported.main(["--help"])
        else:
            imported.main()

    assert calls == [module]
