"""Turn GPU telemetry plus request markers into utilisation evidence.

Inputs:
  - the per-job nvidia-smi CSV written by hpc/ollama_gpu.sbatch (fetch it
    with ``bash hpc/hpc-dev.sh gpu-logs``), and
  - request markers: ``audit_logs/request_markers.jsonl`` from real
    assessments and/or the JSONL written by research/gpu_bench.py.

Each GPU sample is tagged "in flight" if any request was running at that
moment. Per (model, concurrency) group the report gives:

  util_busy_mean      mean utilization.gpu while a request was in flight;
                      how hard the GPU worked when it had work
  util_window_mean    mean utilization.gpu over the whole run, idle gaps included
  idle_gap_fraction   share of the run with NO request in flight: time lost
                      to client-side work between calls, not to the GPU
  vram_peak_pct       peak memory.used / memory.total
  power_busy_pct      mean power.draw while in flight / power.limit
  throttled_fraction  in-flight samples with a thermal or hardware clock slowdown
  power_cap_fraction  in-flight samples flagged SW power cap (0x4). Origami's
                      RTX 3090 sets this bit even idle at ~28 W, so it is
                      reported apart and is not evidence of throttling alone
  output_tok_s        generated tokens / run wall-clock (throughput)
  unanswered_requests requests that got no response (client timeout): the
  unanswered_s        GPU was busy, usually generating without end, for
                      unanswered_s seconds of work that was thrown away
  truncated_prompts   requests whose prompt Ollama cut to fit its context
  length_capped       answers stopped at LLM_MAX_OUTPUT_TOKENS (runaway output)
  decode_bw_eff       (gpu_bench rows only) decode tok/s per request x model
                      bytes in VRAM / memory bandwidth: how close single-stream
                      decode is to the card's bandwidth ceiling

Usage (from ai-engine/):

    python -m research.gpu_report --gpu-csv gpu_logs/12345.gpu.csv \\
        --markers audit_logs/request_markers.jsonl gpu_logs/bench_*.jsonl --mlflow
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# nvidia-smi clocks_throttle_reasons / clocks_event_reasons bits (NVML).
# Thermal and hardware slowdowns mean the GPU was held back. GpuIdle (0x1),
# application clocks (0x2), sync boost (0x10) and display clock (0x100) are
# normal. SW power cap (0x4) is kept separate: this driver sets it at idle.
_SW_POWER_CAP = 0x4
_SLOWDOWN_MASK = 0x8 | 0x20 | 0x40 | 0x80  # HW slowdown, SW thermal, HW thermal, HW power brake

# Peak memory bandwidth (GB/s) by GPU name; most specific names first.
_MEMORY_BANDWIDTH_GBS = [
    ("RTX 3090 Ti", 1008), ("RTX 3090", 936), ("RTX 4090", 1008), ("RTX 3080 Ti", 912),
    ("RTX 3080", 760), ("RTX 2080 Ti", 616), ("TITAN RTX", 672), ("RTX A6000", 768),
    ("RTX A5000", 768), ("A100 80GB", 1935), ("A100", 1555), ("V100", 900), ("A40", 696),
    ("L40S", 864), ("T4", 320),
]


def _column_key(name: str) -> str:
    """'utilization.gpu [%]' -> 'utilization.gpu'; driver-dependent field names unified."""
    key = re.sub(r"\s*\[.*\]$", "", name.strip())
    if key.startswith(("clocks_throttle_reasons", "clocks_event_reasons")):
        return "throttle_reasons"
    return "clocks.sm" if key == "clocks.current.sm" else key


def load_gpu_samples(path: Path, clock_offset_s: float = 0.0) -> pd.DataFrame:
    """Read the sampler CSV. Timestamps are UTC (the sampler runs with TZ=UTC);
    clock_offset_s (cluster minus local) moves them onto the local clock the
    request markers were stamped with."""
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [_column_key(c) for c in df.columns]
    df["time"] = pd.to_datetime(df["timestamp"], format="%Y/%m/%d %H:%M:%S.%f", utc=True)
    df["time"] -= pd.Timedelta(seconds=clock_offset_s)
    for column in ("utilization.gpu", "utilization.memory", "memory.used", "memory.total", "power.draw", "clocks.sm"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")  # "[N/A]" -> NaN
    if "throttle_reasons" in df:
        bits = df["throttle_reasons"].map(_reason_bits)
        df["slowdown"] = (bits & _SLOWDOWN_MASK) != 0
        df["power_cap"] = (bits & _SW_POWER_CAP) != 0
    return df.drop(columns=["timestamp"])


def _reason_bits(value: Any) -> int:
    try:
        return int(str(value).strip(), 16)
    except ValueError:
        return 0


def load_gpu_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    row = pd.read_csv(path, skipinitialspace=True).iloc[0]
    info = {_column_key(str(k)): str(v).strip() for k, v in row.items()}
    limit = re.match(r"[\d.]+", info.get("power.limit", ""))
    return {
        "gpu_name": info.get("name"),
        "driver": info.get("driver_version"),
        "power_limit_w": float(limit.group()) if limit else None,
    }


def memory_bandwidth_gbs(gpu_name: str | None) -> float | None:
    if not gpu_name:
        return None
    return next((float(bw) for name, bw in _MEMORY_BANDWIDTH_GBS if name in gpu_name), None)


def load_markers(paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.dropna(subset=["started_at", "finished_at"])
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True, format="ISO8601")
    df["finished_at"] = pd.to_datetime(df["finished_at"], utc=True, format="ISO8601")
    if "concurrency" not in df:
        df["concurrency"] = np.nan
    # Markers written before run tagging existed: treat each model as one run.
    if "run_id" not in df:
        df["run_id"] = None
    df["run_id"] = df["run_id"].fillna("untagged-" + df["model"].astype(str))
    df["concurrency"] = df["concurrency"].fillna(1).astype(int)
    return df


def _within(times: pd.Series, starts: pd.Series, ends: pd.Series) -> np.ndarray:
    """Boolean mask: which times fall inside any [start, end] interval."""
    t = times.to_numpy("datetime64[ns]")
    mask = np.zeros(len(t), dtype=bool)
    for start, end in zip(starts.to_numpy("datetime64[ns]"), ends.to_numpy("datetime64[ns]")):
        mask |= (t >= start) & (t <= end)
    return mask


def _wasted_work(markers: pd.DataFrame) -> dict[str, Any]:
    """GPU time that produced nothing usable (see the module docstring)."""
    status = pd.to_numeric(markers["http_status"], errors="coerce") if "http_status" in markers else None
    unanswered = markers[status == 0] if status is not None else markers.iloc[0:0]
    unanswered_ms = pd.to_numeric(unanswered["duration_ms"], errors="coerce").sum() if len(unanswered) else 0
    return {
        "unanswered_requests": len(unanswered),
        "unanswered_s": round(float(unanswered_ms) / 1000, 1),
        "truncated_prompts": int(markers["prompt_truncated"].eq(True).sum()) if "prompt_truncated" in markers else 0,
        "length_capped": int(markers["finish_reason"].eq("length").sum()) if "finish_reason" in markers else 0,
    }


def summarise_group(
    samples: pd.DataFrame, markers: pd.DataFrame, gpu_info: dict[str, Any], bandwidth_gbs: float | None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Metrics for one group of markers, plus the GPU samples inside its runs."""
    runs = markers.groupby("run_id").agg(start=("started_at", "min"), end=("finished_at", "max"))
    in_window = _within(samples["time"], runs["start"], runs["end"])
    window = samples.loc[in_window].copy()
    window["in_flight"] = _within(window["time"], markers["started_at"], markers["finished_at"])
    busy = window.loc[window["in_flight"]]

    window_s = float((runs["end"] - runs["start"]).dt.total_seconds().sum())
    output_tokens = (
        pd.to_numeric(markers["completion_tokens"], errors="coerce").sum() if "completion_tokens" in markers else 0
    )
    power_limit = gpu_info.get("power_limit_w")

    def mean(frame: pd.DataFrame, column: str) -> float | None:
        return round(float(frame[column].mean()), 2) if column in frame and len(frame) else None

    metrics: dict[str, Any] = {
        "runs": len(runs),
        "requests": len(markers),
        "samples": len(window),
        "window_s": round(window_s, 1),
        "seconds_per_run": round(window_s / len(runs), 1) if len(runs) else None,
        "util_busy_mean": mean(busy, "utilization.gpu"),
        "util_busy_p50": round(float(busy["utilization.gpu"].median()), 2) if len(busy) else None,
        "util_window_mean": mean(window, "utilization.gpu"),
        "mem_util_busy_mean": mean(busy, "utilization.memory"),
        "idle_gap_fraction": round(1 - float(window["in_flight"].mean()), 4) if len(window) else None,
        "vram_peak_mib": float(window["memory.used"].max()) if len(window) else None,
        "vram_total_mib": float(window["memory.total"].max()) if len(window) else None,
        "power_busy_mean_w": mean(busy, "power.draw"),
        "power_limit_w": power_limit,
        "throttled_fraction": round(float(busy["slowdown"].mean()), 4) if "slowdown" in busy and len(busy) else None,
        "power_cap_fraction": round(float(busy["power_cap"].mean()), 4) if "power_cap" in busy and len(busy) else None,
        "sm_clock_busy_median_mhz": float(busy["clocks.sm"].median()) if "clocks.sm" in busy and len(busy) else None,
        "output_tok_s": round(float(output_tokens) / window_s, 2) if window_s else None,
        **_wasted_work(markers),
    }
    if metrics["vram_peak_mib"] and metrics["vram_total_mib"]:
        metrics["vram_peak_pct"] = round(100 * metrics["vram_peak_mib"] / metrics["vram_total_mib"], 1)
    if metrics["power_busy_mean_w"] and power_limit:
        metrics["power_busy_pct"] = round(100 * metrics["power_busy_mean_w"] / power_limit, 1)

    # Phase timings only exist on gpu_bench rows (native /api/chat).
    if "decode_tok_s" in markers and markers["decode_tok_s"].notna().any():
        metrics["prefill_tok_s_median"] = round(float(markers["prefill_tok_s"].median()), 1)
        metrics["decode_tok_s_median"] = round(float(markers["decode_tok_s"].median()), 2)
        metrics["offload_ratio_min"] = float(markers["offload_ratio"].min()) if markers["offload_ratio"].notna().any() else None
        size_vram = markers["size_vram"].max() if markers["size_vram"].notna().any() else None
        if size_vram and bandwidth_gbs:
            # Weights only (KV-cache reads ignored), so a slight underestimate.
            metrics["decode_bw_eff"] = round(metrics["decode_tok_s_median"] * float(size_vram) / (bandwidth_gbs * 1e9), 3)
    return metrics, window


def plot_timeline(window: pd.DataFrame, title: str, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 3.5))
    t = window["time"]
    ax.plot(t, window["utilization.gpu"], label="GPU util %", linewidth=1)
    ax.plot(t, 100 * window["memory.used"] / window["memory.total"], label="VRAM used %", linewidth=1)
    if "utilization.memory" in window:
        ax.plot(t, window["utilization.memory"], label="memory-bus util %", linewidth=0.8, alpha=0.7)
    ax.fill_between(t, 0, 100, where=window["in_flight"], step="mid", alpha=0.12, label="request in flight")
    ax.set_ylim(0, 105)
    ax.set_ylabel("%")
    ax.set_title(title)
    ax.legend(loc="lower right", fontsize=8, ncol=4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


_TABLE_COLUMNS = [
    "model", "concurrency", "runs", "requests", "seconds_per_run", "util_busy_mean", "util_window_mean",
    "idle_gap_fraction", "vram_peak_pct", "power_busy_pct", "sm_clock_busy_median_mhz", "throttled_fraction",
    "power_cap_fraction", "output_tok_s", "unanswered_requests", "unanswered_s", "truncated_prompts", "length_capped",
    "prefill_tok_s_median", "decode_tok_s_median", "offload_ratio_min", "decode_bw_eff",
]


def to_markdown(summary: pd.DataFrame, group_by: list[str] | None = None) -> str:
    # The group-by fields come first so every row says which configuration it is.
    keys = group_by or ["model", "concurrency"]
    columns = keys + [c for c in _TABLE_COLUMNS if c in summary and c not in keys]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for _, row in summary.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(row[c]) else str(row[c]) for c in columns) + " |")
    return "\n".join(lines) + "\n"


def _default_sibling(gpu_csv: Path, suffix: str) -> Path:
    return gpu_csv.with_name(gpu_csv.name.replace(".gpu.csv", suffix))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gpu-csv", required=True, type=Path, help="<jobid>.gpu.csv from hpc-dev.sh gpu-logs")
    parser.add_argument("--markers", nargs="+", type=Path, default=[Path("audit_logs/request_markers.jsonl")])
    parser.add_argument("--clock-offset", type=float, help="Cluster minus local clock, s (default: <jobid>.clock-offset.txt)")
    parser.add_argument("--group-by", default="model,concurrency", help="Marker fields to group by")
    parser.add_argument("--mem-bandwidth-gbs", type=float, help="Override the GPU's memory bandwidth")
    parser.add_argument("--out-dir", type=Path, help="Default gpu_logs/report_<time>/")
    parser.add_argument("--mlflow", action="store_true", help="Log one MLflow run per group")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    offset_file = _default_sibling(args.gpu_csv, ".clock-offset.txt")
    clock_offset = args.clock_offset
    if clock_offset is None:
        clock_offset = float(offset_file.read_text().strip()) if offset_file.exists() else 0.0

    samples = load_gpu_samples(args.gpu_csv, clock_offset)
    gpu_info = load_gpu_info(_default_sibling(args.gpu_csv, ".gpu-info.csv"))
    bandwidth = args.mem_bandwidth_gbs or memory_bandwidth_gbs(gpu_info.get("gpu_name"))
    markers = load_markers(args.markers)
    if markers.empty:
        raise SystemExit("No request markers found; run an assessment or research/gpu_bench.py first.")
    # Keep only requests the GPU log covers (the markers file spans many jobs).
    markers = markers[(markers["finished_at"] >= samples["time"].min()) & (markers["started_at"] <= samples["time"].max())]
    if markers.empty:
        raise SystemExit("None of the request markers fall inside this GPU log's time range (check --clock-offset).")

    out_dir = args.out_dir or Path(f"gpu_logs/report_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    group_by = [g.strip() for g in args.group_by.split(",")]
    print(f"GPU: {gpu_info.get('gpu_name', 'unknown')} | clock offset {clock_offset:+.3f}s | bandwidth {bandwidth} GB/s")

    rows = []
    for key, group in markers.groupby(group_by):
        labels = dict(zip(group_by, key if isinstance(key, tuple) else (key,)))
        metrics, window = summarise_group(samples, group, gpu_info, bandwidth)
        rows.append({**labels, **metrics})
        slug = "_".join(str(v).replace(":", "-") for v in labels.values())
        if not args.no_plots and len(window):
            plot_timeline(window, f"{labels} on {gpu_info.get('gpu_name', 'GPU')}", out_dir / f"timeline_{slug}.png")
        if args.mlflow:
            _log_to_mlflow(labels, metrics, gpu_info, clock_offset, out_dir / f"timeline_{slug}.png", args.gpu_csv)

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "summary.csv", index=False)
    (out_dir / "summary.md").write_text(to_markdown(summary, group_by), encoding="utf-8")
    print(to_markdown(summary, group_by))
    print(f"Wrote {out_dir}/summary.csv, summary.md" + ("" if args.no_plots else " and timeline_*.png"))


def _log_to_mlflow(
    labels: dict[str, Any], metrics: dict[str, Any], gpu_info: dict[str, Any], clock_offset: float,
    plot: Path, gpu_csv: Path,
) -> None:
    import mlflow

    from llmops.mlflow_config import configure_mlflow

    configure_mlflow()
    mlflow.set_experiment("sprintsight_gpu_utilisation")
    with mlflow.start_run(run_name="gpu_" + "_".join(str(v) for v in labels.values())):
        mlflow.log_params({**labels, **{k: v for k, v in gpu_info.items() if v is not None}, "clock_offset_s": clock_offset})
        mlflow.log_metrics({k: float(v) for k, v in metrics.items() if isinstance(v, (int, float)) and not pd.isna(v)})
        if plot.exists():
            mlflow.log_artifact(str(plot))
        mlflow.log_artifact(str(gpu_csv))


if __name__ == "__main__":
    main()
