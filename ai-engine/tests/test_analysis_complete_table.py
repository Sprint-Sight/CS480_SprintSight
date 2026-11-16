"""comparison_table_complete leaves partial assessments out; zero-citation groundedness is NaN."""

import math

import pandas as pd

from evaluation.offline.analysis import (
    comparison_table,
    comparison_table_complete,
    normalize_groundedness,
)


def _is_nan(value: object) -> bool:
    """NaN or None; takes `object` so it type-checks the same with or without pandas-stubs."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def _row(model, example, *, valid=True, present=6, overall=8.0, rate=1.0, total=4, **extra):
    return {
        "model": model, "example_id": example, "format_valid": valid, "dimensions_present": present,
        "dimensions_total": 6, "overall_score": overall, "groundedness_rate": rate,
        "groundedness_citations_total": total, **extra,
    }


def _df() -> pd.DataFrame:
    return pd.DataFrame([
        _row("a", "e1", overall=6.0),
        _row("a", "e2", overall=8.0),
        _row("a", "e3", valid=False, present=2, overall=10.0),  # partial: 10.0 over two dimensions
        _row("b", "e1", overall=7.0),
        _row("b", "e2", valid=False, present=0, overall=None, rate=None, total=0),  # nothing scored
    ])


def test_partial_rows_do_not_enter_the_complete_overall_score() -> None:
    table = comparison_table_complete(_df())

    assert table.loc["a", "Overall score (0–10) mean"] == 7.0       # not (6+8+10)/3
    assert table.loc["a", "Overall score (0–10) n"] == 2
    assert table.loc["a", "n_partial"] == 1
    assert table.loc["a", "n_rows_total"] == 3
    assert table.loc["b", "n_partial"] == 0                          # failed outright is not partial
    assert "Format validity rate mean" not in table.columns          # 1.0 by construction


def test_the_full_table_still_pools_them_and_reports_n_partial() -> None:
    table = comparison_table(_df())

    assert table.loc["a", "Overall score (0–10) mean"] == 8.0
    assert table.loc["a", "n_partial"] == 1


def test_a_model_with_no_complete_row_stays_in_the_complete_table() -> None:
    df = pd.DataFrame([_row("a", "e1"), _row("c", "e1", valid=False, present=3, overall=9.0)])

    table = comparison_table_complete(df)

    assert table.loc["c", "n_examples"] == 0
    assert table.loc["c", "n_partial"] == 1
    assert _is_nan(table.loc["c", "Overall score (0–10) mean"])


def test_no_complete_row_at_all_gives_an_empty_table_not_an_error() -> None:
    df = pd.DataFrame([_row("a", "e1", valid=False, present=3)])

    table = comparison_table_complete(df)

    assert list(table.index) == ["a"] and table.loc["a", "n_partial"] == 1


def test_old_rows_with_one_point_zero_and_no_citations_become_nan_but_keep_the_old_value() -> None:
    df = pd.DataFrame([_row("a", "e1", rate=1.0, total=0), _row("a", "e2", rate=0.5, total=2)])

    out = normalize_groundedness(df)

    assert _is_nan(out.loc[0, "groundedness_rate"]) and out.loc[1, "groundedness_rate"] == 0.5
    assert list(out["groundedness_rate_legacy"]) == [1.0, 0.5]
    # idempotent
    again = normalize_groundedness(out)
    assert _is_nan(again.loc[0, "groundedness_rate"]) and list(again["groundedness_rate_legacy"]) == [1.0, 0.5]


def test_a_perfect_rate_with_citations_is_not_touched() -> None:
    out = normalize_groundedness(pd.DataFrame([_row("a", "e1", rate=1.0, total=3)]))
    assert out.loc[0, "groundedness_rate"] == 1.0


def test_the_table_averages_groundedness_over_rows_that_cited_something() -> None:
    df = pd.DataFrame([_row("a", "e1", rate=1.0, total=0), _row("a", "e2", rate=0.5, total=2)])

    table = comparison_table(df)

    assert table.loc["a", "Citation groundedness mean"] == 0.5
    assert table.loc["a", "Citation groundedness n"] == 1
    assert table.loc["a", "Citation groundedness, no citations = 1.0 (legacy) mean"] == 0.75


def test_new_rows_with_null_groundedness_use_their_own_legacy_value() -> None:
    df = pd.DataFrame([_row("a", "e1", rate=None, total=0, groundedness_rate_legacy=1.0)])

    out = normalize_groundedness(df)

    assert _is_nan(out.loc[0, "groundedness_rate"]) and out.loc[0, "groundedness_rate_legacy"] == 1.0
