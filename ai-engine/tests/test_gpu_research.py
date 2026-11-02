import json
import sys

import pandas as pd
import pytest

from research import gpu_bench, gpu_report
from services import audit_logger

GPU_CSV = "\n".join(
    [
        (
            "timestamp, utilization.gpu [%], utilization.memory [%], memory.used [MiB], memory.total [MiB], "
            "power.draw [W], clocks.sm [MHz], temperature.gpu, clocks_throttle_reasons.active"
        ),
    ]
    + [
        f"2026/11/02 06:00:{second:02d}.000, {90 if second in (2, 3, 4, 6, 7) else 0}, 40, "
        f"{20000 if second >= 2 else 1000}, 24576, {300 if second in (2, 3, 4, 6, 7) else 25}.00, 1695, 60, "
        f"{'0x0000000000000004' if second == 3 else '0x0000000000000001'}"
        for second in range(10)
    ]
) + "\n"
GPU_INFO = "name, driver_version, memory.total [MiB], power.limit [W]\nNVIDIA GeForce RTX 3090, 550.54, 24576 MiB, 350.00 W\n"


def _marker(start: int, end: int, **extra) -> dict:
    return {
        "run_id": "run-1",
        "model": "sprintsight-llama31",
        "concurrency": 2,
        "started_at": f"2026-11-02T06:00:{start:02d}+00:00",
        "finished_at": f"2026-11-02T06:00:{end:02d}+00:00",
        "completion_tokens": 300,
        **extra,
    }


# ── research/gpu_bench.py ────────────────────────────────────────────────────

def test_load_prompts_replays_audit_records(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_logger, "AUDIT_LOG_DIR", tmp_path)
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    request = {
        "model": "sprintsight-qwen",
        "messages": [{"role": "user", "content": "grade this"}],
        "temperature": 0,
        "options": {"num_ctx": 32000},
        "response_format": {"type": "json_schema", "json_schema": {"name": "ModelOutput", "schema": schema}},
    }
    base = {"request_id": "r1", "dimension": "testing", "model": "sprintsight-qwen"}
    audit_logger.write_audit_record({**base, "request": request, "raw_response": "{}"})
    # The citation-grounding note logs the same request again (as a raw string).
    audit_logger.write_audit_record({**base, "request": json.dumps(request), "ungrounded_citations_dropped": []})
    audit_logger.write_audit_record({**base, "request": request, "error": "timeout"})
    audit_logger.write_audit_record({**base, "model": "sprintsight-mistral", "request": request})

    prompts = gpu_bench.load_prompts(tmp_path, "sprintsight-qwen", None)
    assert len(prompts) == 1
    assert prompts[0]["format"] == schema
    assert prompts[0]["options"] == {"num_ctx": 32000}

    body = gpu_bench.build_native_request(prompts[0], "sprintsight-llama31", 32000, 1024)
    assert body["model"] == "sprintsight-llama31"
    assert body["stream"] is False
    assert body["options"] == {"temperature": 0, "num_ctx": 32000, "num_batch": 1024}
    assert body["format"] == schema


def test_timing_fields_converts_ollama_durations():
    fields = gpu_bench.timing_fields(
        {
            "prompt_eval_count": 1000, "prompt_eval_duration": 500_000_000,
            "eval_count": 100, "eval_duration": 2_000_000_000,
            "load_duration": 3_000_000_000, "total_duration": 5_600_000_000,
        },
        num_ctx=1000,
    )
    assert fields["prefill_tok_s"] == 2000.0
    assert fields["decode_tok_s"] == 50.0
    assert fields["load_s"] == 3.0
    assert fields["prompt_truncated"] is True
    assert gpu_bench.timing_fields({}, None)["decode_tok_s"] is None


# ── research/gpu_report.py ───────────────────────────────────────────────────

def test_gpu_report_separates_busy_time_from_idle_gaps(tmp_path):
    (tmp_path / "1.gpu.csv").write_text(GPU_CSV)
    samples = gpu_report.load_gpu_samples(tmp_path / "1.gpu.csv")
    (tmp_path / "1.gpu-info.csv").write_text(GPU_INFO)
    info = gpu_report.load_gpu_info(tmp_path / "1.gpu-info.csv")
    assert info["power_limit_w"] == 350.0
    assert gpu_report.memory_bandwidth_gbs(info["gpu_name"]) == 936

    # One run: two requests with a 1-second gap (sample 5) between them.
    markers = pd.DataFrame([_marker(2, 4), _marker(6, 7)])
    for column in ("started_at", "finished_at"):
        markers[column] = pd.to_datetime(markers[column], utc=True)
    metrics, window = gpu_report.summarise_group(samples, markers, info, 936)

    assert metrics["samples"] == 6                         # seconds 2..7
    assert metrics["idle_gap_fraction"] == round(1 / 6, 4)  # only second 5 idle
    assert metrics["util_busy_mean"] == 90
    assert metrics["util_window_mean"] == 75
    assert metrics["throttled_fraction"] == 0.2             # power-cap bit at second 3
    assert metrics["vram_peak_pct"] == round(100 * 20000 / 24576, 1)
    assert metrics["power_busy_pct"] == round(100 * 300 / 350, 1)
    assert metrics["output_tok_s"] == 120.0                 # 600 tokens over 5 s
    assert window["in_flight"].sum() == 5


def test_gpu_report_applies_clock_offset(tmp_path):
    (tmp_path / "1.gpu.csv").write_text(GPU_CSV)
    shifted = gpu_report.load_gpu_samples(tmp_path / "1.gpu.csv", clock_offset_s=3600)
    assert shifted["time"].iloc[0] == pd.Timestamp("2026-11-02T05:00:00Z")


def test_gpu_report_cli_writes_summary_and_plot(tmp_path, monkeypatch):
    (tmp_path / "7.gpu.csv").write_text(GPU_CSV)
    (tmp_path / "7.gpu-info.csv").write_text(GPU_INFO)
    (tmp_path / "7.clock-offset.txt").write_text("0.0\n")
    bench_row = _marker(2, 4, decode_tok_s=110.0, prefill_tok_s=3000.0, size_vram=5_000_000_000, offload_ratio=1.0)
    markers = tmp_path / "markers.jsonl"
    markers.write_text("\n".join(json.dumps(m) for m in [bench_row, _marker(6, 7)]) + "\n")
    out_dir = tmp_path / "report"

    monkeypatch.setattr(sys, "argv", [
        "gpu_report", "--gpu-csv", str(tmp_path / "7.gpu.csv"), "--markers", str(markers), "--out-dir", str(out_dir),
    ])
    gpu_report.main()

    summary = pd.read_csv(out_dir / "summary.csv")
    assert summary.loc[0, "model"] == "sprintsight-llama31"
    assert summary.loc[0, "idle_gap_fraction"] == pytest.approx(1 / 6, abs=1e-3)
    assert summary.loc[0, "decode_bw_eff"] == pytest.approx(110 * 5e9 / 936e9, abs=1e-3)
    assert (out_dir / "summary.md").read_text().startswith("| model | concurrency |")
    assert (out_dir / "timeline_sprintsight-llama31_2.png").exists()
