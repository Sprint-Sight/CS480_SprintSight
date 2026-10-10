"""Report-ready plots for the model-comparison pipeline.

Scope is deliberately narrow — four plots that cover the three concerns
(quality / reliability / performance) plus one headline pairwise figure.
Every plot:
    - uses matplotlib only (no seaborn), so the ai-engine env doesn't grow
    - returns the Figure object (caller controls save/show)
    - takes the SAME long-format DataFrame produced by analysis.load_runs

The small-N regime (3–5 examples per model) means box plots and KDEs can
mislead the reader. Where in doubt the code uses strip-plots + point
estimates with the SD annotated numerically.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.eval.analysis import pairwise_ci_table

log = logging.getLogger(__name__)


def _apply_minimal_style(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.3)


def plot_latency_distribution(df: pd.DataFrame, figsize: tuple[float, float] = (6, 4)) -> plt.Figure:
    """Per-model strip of latency_s with mean marker. Honest at small N
    because every point is visible; no distributional assumption."""
    fig, ax = plt.subplots(figsize=figsize)
    models = sorted(df["model"].dropna().unique())
    xticks = []
    for i, model in enumerate(models):
        values = pd.to_numeric(df.loc[df["model"] == model, "latency_s"], errors="coerce").dropna()
        if values.empty:
            continue
        jitter = (np.random.default_rng(42).random(len(values)) - 0.5) * 0.2
        ax.scatter(np.full_like(values, i, dtype=float) + jitter, values, alpha=0.6, s=36)
        ax.scatter([i], [values.mean()], marker="_", s=400, color="black", zorder=3)
        xticks.append(f"{model}\nmean={values.mean():.1f}s")
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(xticks, fontsize=9)
    ax.set_ylabel("Latency per full-sprint evaluation (s)")
    ax.set_title("Latency distribution by model")
    _apply_minimal_style(ax)
    fig.tight_layout()
    return fig


def plot_success_rate(df: pd.DataFrame, figsize: tuple[float, float] = (6, 4)) -> plt.Figure:
    """Format-validity rate per model. The reliability axis."""
    fig, ax = plt.subplots(figsize=figsize)
    series = (
        df.groupby("model")["format_valid"]
        .agg(["mean", "count"])
        .sort_index()
    )
    bars = ax.bar(series.index, series["mean"], color="#4a7fb0")
    for bar, (model, row) in zip(bars, series.iterrows()):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{row['mean']:.0%}\nn={int(row['count'])}",
            ha="center", va="bottom", fontsize=9,
        )
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Format-validity rate")
    ax.set_title("Model reliability — format-validity rate")
    _apply_minimal_style(ax)
    fig.tight_layout()
    return fig


def plot_token_distribution(df: pd.DataFrame, figsize: tuple[float, float] = (6, 4)) -> plt.Figure:
    """Output token count per model. Skipped silently if the runner didn't
    capture tokens (current evaluator.py returns None)."""
    fig, ax = plt.subplots(figsize=figsize)
    models = sorted(df["model"].dropna().unique())
    anything = False
    for i, model in enumerate(models):
        values = pd.to_numeric(
            df.loc[df["model"] == model, "tokens_completion"], errors="coerce"
        ).dropna()
        if values.empty:
            continue
        anything = True
        ax.scatter(np.full(len(values), i, dtype=float), values, alpha=0.6, s=36)
    if not anything:
        ax.text(
            0.5, 0.5,
            "No token data recorded.\nSee research/eval/README.md "
            "for how to populate tokens_* from audit logs.",
            ha="center", va="center", transform=ax.transAxes,
        )
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, fontsize=9)
    ax.set_ylabel("Completion tokens")
    ax.set_title("Output token distribution by model")
    _apply_minimal_style(ax)
    fig.tight_layout()
    return fig


def plot_pairwise_differences(
    df: pd.DataFrame,
    metric: str = "overall_score",
    figsize: tuple[float, float] = (6, 3.5),
) -> plt.Figure:
    """Headline figure: mean paired difference ± 95% bootstrap CI, one
    horizontal bar per model pair. If the CI crosses 0, the reader sees it
    immediately — that is the whole point of this figure."""
    table = pairwise_ci_table(df, metric=metric)
    table = table.dropna(subset=["mean_diff"])
    fig, ax = plt.subplots(figsize=figsize)
    if table.empty:
        ax.text(0.5, 0.5, f"Not enough paired data for metric {metric!r}.",
                ha="center", va="center", transform=ax.transAxes)
        return fig

    y = np.arange(len(table))
    err_low = table["mean_diff"] - table["ci_low"]
    err_high = table["ci_high"] - table["mean_diff"]
    ax.errorbar(
        table["mean_diff"], y,
        xerr=[err_low, err_high],
        fmt="o", color="#2b4f70", capsize=4,
    )
    ax.axvline(0, color="gray", linestyle="--", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(table["pair"], fontsize=9)
    ax.set_xlabel(f"Mean difference ({metric}, A − B)  with 95% bootstrap CI")
    ax.set_title(f"Pairwise comparison on {metric}")
    _apply_minimal_style(ax)
    fig.tight_layout()
    return fig


def save_all(df: pd.DataFrame, out_dir: str | Path, metric_for_pairwise: str = "overall_score") -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, fig in [
        ("latency_distribution", plot_latency_distribution(df)),
        ("format_validity_rate", plot_success_rate(df)),
        ("token_distribution", plot_token_distribution(df)),
        (f"pairwise_{metric_for_pairwise}", plot_pairwise_differences(df, metric=metric_for_pairwise)),
    ]:
        path = out / f"{name}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths
