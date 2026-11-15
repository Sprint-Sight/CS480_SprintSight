"""`cli analyze` says when the runs it pools should not be averaged together."""

import pandas as pd

from evaluation.offline.analysis import mixed_run_warnings, run_summary


def _rows(run_id: str, *, dataset="d_real_sprints", digest="h1", phase="final", n=2, model="m"):
    return [
        {"mlflow_run_id": run_id, "model": model, "dataset_name": dataset,
         "dataset_hash": digest, "phase": phase, "example_id": f"e{i}"}
        for i in range(n)
    ]


def test_one_dataset_version_and_one_phase_is_clean() -> None:
    df = pd.DataFrame(_rows("r1", model="a") + _rows("r2", model="b"))

    assert mixed_run_warnings(df) == []
    summary = run_summary(df)
    assert list(summary["mlflow_run_id"]) == ["r1", "r2"]
    assert list(summary["n_examples"]) == [2, 2]


def test_a_reexported_dataset_is_flagged_with_the_filter_for_one_version() -> None:
    df = pd.DataFrame(_rows("old", digest="aaa") + _rows("new", digest="bbb"))

    [warning] = mixed_run_warnings(df)

    assert "d_real_sprints changed between runs" in warning
    assert "params.dataset_hash" in warning


def test_mixed_phases_and_datasets_are_each_flagged() -> None:
    df = pd.DataFrame(
        _rows("smoke", dataset="d1_fixtures", digest="s", phase="smoke") + _rows("final")
    )

    warnings = mixed_run_warnings(df)

    assert any("2 datasets" in w for w in warnings)
    assert any("2 phases" in w and "params.phase" in w for w in warnings)


def test_runs_from_before_the_phase_was_recorded_still_summarise() -> None:
    df = pd.DataFrame(_rows("r1")).drop(columns=["phase", "dataset_hash"])

    assert mixed_run_warnings(df) == []
    assert list(run_summary(df).columns) == ["mlflow_run_id", "model", "dataset_name", "n_examples"]


def _with(df: pd.DataFrame, **columns) -> pd.DataFrame:
    for name, value in columns.items():
        df[name] = value
    return df


def test_one_model_with_two_prompt_hashes_is_flagged() -> None:
    df = pd.concat([
        _with(pd.DataFrame(_rows("old")), prompt_hash="aaa"),
        _with(pd.DataFrame(_rows("new")), prompt_hash="bbb"),
    ])

    [warning] = mixed_run_warnings(df)

    assert "model m was run with 2 different prompt text" in warning
    assert "params.prompt_hash" in warning


def test_one_model_with_two_digests_is_flagged() -> None:
    df = pd.concat([
        _with(pd.DataFrame(_rows("a")), model_digest="d1"),
        _with(pd.DataFrame(_rows("b")), model_digest="d2"),
    ])

    [warning] = mixed_run_warnings(df)

    assert "model weights" in warning and "params.model_digest" in warning


def test_different_models_or_unrecorded_hashes_are_not_flagged() -> None:
    df = pd.concat([
        _with(pd.DataFrame(_rows("a", model="x")), prompt_hash="aaa"),
        _with(pd.DataFrame(_rows("b", model="y")), prompt_hash="bbb"),   # another model: fine
        _with(pd.DataFrame(_rows("c", model="x")), prompt_hash=None),    # predates the param: ignored
        _with(pd.DataFrame(_rows("d", model="x")), prompt_hash="None"),  # MLflow's stringified None
    ])

    assert mixed_run_warnings(df) == []
