"""Report figures for the GPU utilisation results.

    before-after  Two stacked GPU timelines on the same axes: GPU utilisation
                  (solid) and power draw as % of the card's limit (dashed),
                  from the first request of each run to its last.
    models        One row per model, four small panels: GPU utilisation while
                  busy, power, the model's own VRAM, and assessment time. Each
                  panel has its own axis, so no two scales share one.

Runs are picked by a run_id prefix or a gpu_bench --label. Usage (from
ai-engine/, venv active):

    python -m research.gpu_figures before-after \\
        --before-csv gpu_logs/349942.gpu.csv --before-markers gpu_logs/bench_*recorded*.jsonl \\
        --before-run recorded --before-title "As deployed: Ollama's default CPU threads" \\
        --after-csv gpu_logs/349942.gpu.csv --after-markers gpu_logs/bench_*threads4*.jsonl \\
        --after-run threads4 --after-title "CPU threads pinned to the job's 4 cores" \\
        --out gpu_logs/figures/gpu_before_after

    python -m research.gpu_figures models --gpu-csv gpu_logs/351110.gpu.csv \\
        --runs dc12b5c5 ae69e2a6 24d3ab9f 71a3b0e5 b8e01d8f 6cc85348 \\
        --out gpu_logs/figures/gpu_per_model

Each figure is written as <out>.png (200 dpi) and <out>.pdf (vector, for the report).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from research import gpu_report

# Validated with the dataviz skill's palette checker (light surface).
UTIL_COLOUR = "#2a78d6"
POWER_COLOUR = "#eb6834"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"

MODEL_NAMES = {
    "sprintsight-qwen": "qwen3-8b",
    "sprintsight-llama31": "llama3.1-8b",
    "sprintsight-mistral": "mistral-7b",
    "sprintsight-gemma": "gemma4-12b",
    "sprintsight-qwen25-32b": "qwen2.5-32b",
    "sprintsight-coder-32b": "qwen2.5-coder-32b",
    "sprintsight-r1-32b": "deepseek-r1-32b",
}

plt.rcParams.update({
    "font.size": 9, "axes.titlesize": 9.5, "axes.labelsize": 9,
    "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY,
    "axes.spines.top": False, "axes.spines.right": False,
})


def _sibling(gpu_csv: Path, suffix: str) -> Path:
    return gpu_csv.with_name(gpu_csv.name.replace(".gpu.csv", suffix))


def load_job(gpu_csv: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """GPU samples on the local clock, plus the job's GPU info."""
    offset_file = _sibling(gpu_csv, ".clock-offset.txt")
    offset = float(offset_file.read_text().strip()) if offset_file.exists() else 0.0
    return gpu_report.load_gpu_samples(gpu_csv, offset), gpu_report.load_gpu_info(_sibling(gpu_csv, ".gpu-info.csv"))


def select_run(markers: pd.DataFrame, selector: str) -> pd.DataFrame:
    """Markers of one run, picked by run_id prefix or gpu_bench label."""
    by_label = markers["label"].eq(selector) if "label" in markers else pd.Series(False, index=markers.index)
    picked = markers[markers["run_id"].astype(str).str.startswith(selector) | by_label]
    if picked.empty:
        raise SystemExit(f"No requests match run '{selector}'.")
    if picked["run_id"].nunique() > 1:
        raise SystemExit(f"'{selector}' matches {picked['run_id'].nunique()} runs; give a longer run_id prefix.")
    return picked


def run_timeline(samples: pd.DataFrame, run: pd.DataFrame, power_limit: float) -> dict[str, Any]:
    start, end = run["started_at"].min(), run["finished_at"].max()
    window = samples[(samples["time"] >= start) & (samples["time"] <= end)]
    return {
        "seconds": (window["time"] - start).dt.total_seconds().to_numpy(),
        "util": window["utilization.gpu"].to_numpy(),
        "power_pct": (100 * window["power.draw"] / power_limit).to_numpy(),
        "duration": (end - start).total_seconds(),
        "util_mean": float(window["utilization.gpu"].mean()),
        "power_mean": float(100 * window["power.draw"].mean() / power_limit),
    }


def plot_before_after(before: dict[str, Any], after: dict[str, Any], titles: tuple[str, str], xlabel: str, out: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.9), sharex=True, sharey=True)
    x_max = max(before["duration"], after["duration"]) * 1.04
    for ax, panel, letter, title in zip(axes, (before, after), "ab", titles):
        ax.plot(panel["seconds"], panel["util"], color=UTIL_COLOUR, linewidth=1.3, label="GPU utilisation")
        ax.plot(panel["seconds"], panel["power_pct"], color=POWER_COLOUR, linewidth=1.3, linestyle=(0, (4, 2.5)),
                label="Power draw (% of limit)")
        ax.axvline(panel["duration"], color=INK_SECONDARY, linewidth=0.8, linestyle=":")
        ax.annotate(f"finished\n{panel['duration']:.0f} s", (panel["duration"], 50), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=INK_SECONDARY)
        ax.set_title(f"({letter}) {title}", loc="left", pad=16)
        ax.text(0, 1.02, f"mean GPU utilisation {panel['util_mean']:.0f}%  ·  mean power {panel['power_mean']:.0f}% of limit",
                transform=ax.transAxes, fontsize=8.5, color=INK_SECONDARY)
        ax.set_ylim(0, 105)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylabel("%")
        ax.set_xlim(0, x_max)
        ax.grid(axis="y", color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)
    axes[1].set_xlabel(xlabel)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save(fig, out)


def model_rows(samples: pd.DataFrame, info: dict[str, Any], markers: pd.DataFrame,
               selectors: list[str], names: list[str] | None) -> list[dict[str, Any]]:
    rows = []
    for i, selector in enumerate(selectors):
        run = select_run(markers, selector)
        metrics, _ = gpu_report.summarise_group(samples, run, info, None)
        model = str(run["model"].iloc[0])
        rows.append({
            "name": names[i] if names else MODEL_NAMES.get(model, model),
            "util": metrics["util_busy_mean"],
            "power": metrics.get("power_busy_pct"),
            "vram": metrics.get("vram_model_pct"),
            "seconds": metrics["seconds_per_run"],
        })
    return rows


def plot_models(rows: list[dict[str, Any]], flagged: dict[str, str], power_limit: float | None, out: Path) -> None:
    panels = [
        ("util", "GPU utilisation\nwhile busy (%)", 100),
        ("power", f"Power draw\n(% of {power_limit:.0f} W limit)" if power_limit else "Power draw (% of limit)", 100),
        ("vram", "VRAM used by the\nmodel (% of 24 GB)", 100),
        ("seconds", "Assessment time (s)", None),
    ]
    names = [r["name"] for r in rows]
    fig, axes = plt.subplots(1, len(panels), figsize=(7.4, 0.42 * len(rows) + 1.3), sharey=True)
    for ax, (key, label, limit) in zip(axes, panels):
        values = [r[key] or 0 for r in rows]
        bars = ax.barh(names, values, height=0.68, color=UTIL_COLOUR)
        for bar, row in zip(bars, rows):
            if row["name"] in flagged:
                bar.set_hatch("////")
                bar.set_facecolor("white")
                bar.set_edgecolor(UTIL_COLOUR)
        top = limit or max(values) * 1.28
        ax.set_xlim(0, top)
        for y, value in enumerate(values):
            ax.text(value + top * 0.02, y, f"{value:.0f}", va="center", fontsize=8, color=INK)
        ax.set_title(label, loc="left", fontsize=8.5)
        ax.grid(axis="x", color=GRID, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    axes[0].invert_yaxis()
    if flagged:
        note = "   ".join(f"Hatched: {name}: {text}" for name, text in flagged.items())
        fig.text(0.01, 0.01, note, fontsize=7.5, color=INK_SECONDARY)
    fig.tight_layout(rect=(0, 0.05 if flagged else 0, 1, 1))
    _save(fig, out)


def _save(fig: plt.Figure, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out.with_suffix('.png')} and {out.with_suffix('.pdf')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="figure", required=True)

    ba = sub.add_parser("before-after", help="Two GPU timelines, before and after a change")
    for side in ("before", "after"):
        ba.add_argument(f"--{side}-csv", required=True, type=Path, help="<jobid>.gpu.csv covering the run")
        ba.add_argument(f"--{side}-markers", nargs="+", type=Path, default=[Path("audit_logs/request_markers.jsonl")])
        ba.add_argument(f"--{side}-run", required=True, help="run_id prefix or gpu_bench --label")
        ba.add_argument(f"--{side}-title", required=True)
    ba.add_argument("--xlabel", default="Seconds since first request")
    ba.add_argument("--out", type=Path, default=Path("gpu_logs/figures/gpu_before_after"))

    mo = sub.add_parser("models", help="Per-model GPU use, one row per run")
    mo.add_argument("--gpu-csv", required=True, type=Path)
    mo.add_argument("--markers", nargs="+", type=Path, default=[Path("audit_logs/request_markers.jsonl")])
    mo.add_argument("--runs", nargs="+", required=True, help="run_id prefixes, top to bottom")
    mo.add_argument("--names", nargs="+", help="Display names (default: from the model id)")
    mo.add_argument("--flag", nargs=2, action="append", default=[], metavar=("NAME", "NOTE"),
                    help="Hatch a row and footnote it, e.g. --flag mistral-7b 'includes an 18-min stall'")
    mo.add_argument("--out", type=Path, default=Path("gpu_logs/figures/gpu_per_model"))
    args = parser.parse_args()

    if args.figure == "before-after":
        panels = []
        for side in ("before", "after"):
            samples, info = load_job(getattr(args, f"{side}_csv"))
            run = select_run(gpu_report.load_markers(getattr(args, f"{side}_markers")), getattr(args, f"{side}_run"))
            panels.append(run_timeline(samples, run, info.get("power_limit_w") or 350.0))
        plot_before_after(panels[0], panels[1], (args.before_title, args.after_title), args.xlabel, args.out)
    else:
        if args.names and len(args.names) != len(args.runs):
            raise SystemExit("--names needs one name per --runs entry.")
        samples, info = load_job(args.gpu_csv)
        rows = model_rows(samples, info, gpu_report.load_markers(args.markers), args.runs, args.names)
        plot_models(rows, dict(args.flag), info.get("power_limit_w"), args.out)


if __name__ == "__main__":
    main()
