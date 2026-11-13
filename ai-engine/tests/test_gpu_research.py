import json
import sys

import pandas as pd
import pytest

from research.gpu import bench as gpu_bench
from research.gpu import report as gpu_report
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


# ── research/gpu/bench.py ────────────────────────────────────────────────────

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


# ── research/gpu/report.py ───────────────────────────────────────────────────

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
    assert metrics["throttled_fraction"] == 0               # 0x4 is power cap, not a slowdown
    assert metrics["power_cap_fraction"] == 0.2             # power-cap bit at second 3
    assert metrics["sm_clock_busy_median_mhz"] == 1695
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


def test_slowdown_bits_follow_nvml(tmp_path):
    header = (
        "timestamp, utilization.gpu [%], memory.used [MiB], memory.total [MiB], "
        "clocks.current.sm [MHz], clocks_event_reasons.active"
    )
    rows = [
        "2026/11/02 06:00:00.000, 50, 1, 2, 1695, 0x0000000000000020",  # SW thermal slowdown
        "2026/11/02 06:00:01.000, 50, 1, 2, 1695, 0x0000000000000100",  # display clock: normal
        "2026/11/02 06:00:02.000, 50, 1, 2, 1695, 0x0000000000000004",  # SW power cap: separate
        "2026/11/02 06:00:03.000, 50, 1, 2, 1695, [N/A]",
    ]
    (tmp_path / "2.gpu.csv").write_text("\n".join([header, *rows]) + "\n")
    samples = gpu_report.load_gpu_samples(tmp_path / "2.gpu.csv")
    assert samples["slowdown"].tolist() == [True, False, False, False]
    assert samples["power_cap"].tolist() == [False, False, True, False]
    assert samples["clocks.sm"].tolist() == [1695] * 4         # newer drivers' column name


def test_uncached_gives_every_request_a_unique_prefix():
    messages = [{"role": "system", "content": "schema"}, {"role": "user", "content": "grade"}]
    first, second = gpu_bench.uncached(messages), gpu_bench.uncached(messages)
    assert first[0]["content"] != second[0]["content"]
    assert first[0]["content"].endswith("\nschema")
    assert first[1] == messages[1]
    assert messages[0]["content"] == "schema"  # input left untouched


def test_summary_table_starts_with_group_by_columns():
    summary = pd.DataFrame([{"model": "m", "label": "threads4", "concurrency": 1, "decode_tok_s_median": 60.3}])
    table = gpu_report.to_markdown(summary, ["model", "label"])
    assert table.startswith("| model | label | concurrency | decode_tok_s_median |")
    assert "| m | threads4 | 1 | 60.3 |" in table


def test_build_native_request_format_and_thread_overrides():
    prompt = {"messages": [{"role": "user", "content": "x"}], "temperature": 0, "format": "json"}
    assert gpu_bench.build_native_request(prompt, "m", None, None)["format"] == "json"
    unconstrained = gpu_bench.build_native_request(prompt, "m", None, None, num_thread=4, output_format="none")
    assert "format" not in unconstrained
    assert unconstrained["options"] == {"temperature": 0, "num_thread": 4}
    assert "format" not in gpu_bench.build_native_request({**prompt, "format": None}, "m", None, None)


def test_wasted_work_counts_unanswered_truncated_and_capped_requests():
    markers = pd.DataFrame([
        {"http_status": 200, "duration_ms": 10_000, "prompt_truncated": False, "finish_reason": "stop"},
        {"http_status": 0, "duration_ms": 1_200_000, "prompt_truncated": None, "finish_reason": None},
        {"http_status": 200, "duration_ms": 5_000, "prompt_truncated": True, "finish_reason": "length"},
    ])
    assert gpu_report._wasted_work(markers) == {
        "unanswered_requests": 1, "unanswered_s": 1200.0, "truncated_prompts": 1, "length_capped": 1,
    }
    # Markers written before these fields existed still summarise.
    assert gpu_report._wasted_work(pd.DataFrame([{"duration_ms": 1}]))["unanswered_requests"] == 0


def test_bench_replays_the_apps_answer_cap():
    prompt = {"messages": [{"role": "user", "content": "x"}], "temperature": 0, "options": {"num_predict": 8192}}
    assert gpu_bench.build_native_request(prompt, "m", None, None)["options"]["num_predict"] == 8192
    assert gpu_bench.timing_fields({"done_reason": "length"}, None)["finish_reason"] == "length"


def test_load_prompts_maps_max_tokens_to_num_predict(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_logger, "AUDIT_LOG_DIR", tmp_path)
    request = {"model": "m", "messages": [{"role": "user", "content": "x"}], "max_tokens": 8192}
    audit_logger.write_audit_record({"request_id": "r", "dimension": "testing", "model": "m", "request": request})
    [prompt] = gpu_bench.load_prompts(tmp_path, "m", None)
    assert prompt["options"] == {"num_predict": 8192}


def _memory_samples(levels: list[int]) -> pd.DataFrame:
    times = pd.date_range("2026-11-03T06:00:00Z", periods=len(levels), freq="1s")
    return pd.DataFrame({"time": times, "memory.used": levels})


def _run(start: int, first_end: int, end: int) -> pd.DataFrame:
    base = pd.Timestamp("2026-11-03T06:00:00Z")
    return pd.DataFrame({
        "started_at": [base + pd.Timedelta(seconds=start), base + pd.Timedelta(seconds=first_end)],
        "finished_at": [base + pd.Timedelta(seconds=first_end), base + pd.Timedelta(seconds=end)],
    })


def test_model_vram_ignores_models_left_loaded_from_earlier_runs():
    # 7,164 MiB of an earlier model stays resident; this model adds 6,805.
    samples = _memory_samples([7164] * 12 + [13969] * 20)
    assert gpu_report.model_vram_mib(samples, _run(10, 20, 30)) == 6805
    # The earlier model is unloaded first, then this one loads: still its own size.
    samples = _memory_samples([20198] * 11 + [1] * 3 + [7162] * 18)
    assert gpu_report.model_vram_mib(samples, _run(10, 20, 30)) == 7161
    # Already loaded (no rise): the run's median.
    samples = _memory_samples([7164] * 32)
    assert gpu_report.model_vram_mib(samples, _run(10, 20, 30)) == 7164
