"""Replay real grading prompts against Ollama to measure GPU throughput.

The app talks to Ollama's OpenAI-compatible /v1 endpoint, which returns token
counts but no timings. This harness replays the exact requests recorded in
the audit logs (``audit_logs/llm_*.txt``) against Ollama's native /api/chat,
which also returns how long prefill (reading the prompt) and decode (writing
the answer) took and whether the model had to be loaded first. It replays
them at each requested concurrency level and writes one JSON line per request
in the same shape as the app's request markers, so research/gpu/report.py
can line both up with the GPU telemetry.

Ollama only runs OLLAMA_NUM_PARALLEL requests at once (set on the GPU job).
A concurrency level above that just queues on the server, so submit the job
with OLLAMA_NUM_PARALLEL >= the highest level you sweep.

Usage (from ai-engine/, venv active, HPC tunnel open; run an assessment with
the same model first so the audit logs have prompts to replay):

    python -m research.gpu.bench --model sprintsight-llama31 --concurrency 1,2,4

To find what limits decode speed, compare runs that change one thing:
``--format none`` drops the JSON output constraint (grammar sampling runs on
the CPU for every generated token), and ``--num-thread 4`` matches Ollama's
CPU threads to the 4 CPUs the Slurm job reserves.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from services.llm_client import find_loaded_model, parse_loaded_models

_METADATA_HEADER = "METADATA\n--------\n"
_REQUEST_HEADER = "\n\nINPUT SENT TO OLLAMA\n--------------------\n"
_RESPONSE_HEADER = "\n\nRAW OUTPUT FROM OLLAMA\n"
_NS = 1e9


def parse_audit_record(text: str) -> dict[str, Any] | None:
    """Split one audit_logger record into its metadata and request JSON.
    Returns None for records with no replayable request (errors, notes)."""
    if _METADATA_HEADER not in text or _REQUEST_HEADER not in text:
        return None
    metadata_text, _, rest = text.split(_METADATA_HEADER, 1)[1].partition(_REQUEST_HEADER)
    request_text = rest.split(_RESPONSE_HEADER, 1)[0]
    try:
        metadata = json.loads(metadata_text)
        request = json.loads(request_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(request, dict) or not request.get("messages"):
        return None
    return {"metadata": metadata, "request": request}


def _native_format(request: dict[str, Any]) -> Any:
    """OpenAI response_format -> Ollama's native `format` field."""
    response_format = request.get("response_format") or {}
    if response_format.get("type") == "json_schema":
        return (response_format.get("json_schema") or {}).get("schema") or "json"
    if response_format.get("type") == "json_object":
        return "json"
    return None


def load_prompts(audit_dir: Path, source_model: str | None, limit: int | None) -> list[dict[str, Any]]:
    """Unique replayable requests from the audit logs, oldest first."""
    prompts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(audit_dir.glob("llm_*.txt")):
        record = parse_audit_record(path.read_text(encoding="utf-8"))
        if record is None or "error" in record["metadata"]:
            continue
        metadata, request = record["metadata"], record["request"]
        if source_model and metadata.get("model") != source_model:
            continue
        # The citation-grounding note re-logs the same request; dedupe on content.
        digest = hashlib.sha256(json.dumps(request["messages"], sort_keys=True).encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        options = dict(request.get("options") or {})
        if request.get("max_tokens"):
            options["num_predict"] = request["max_tokens"]  # the app's answer cap, in native form
        prompts.append({
            "dimension": metadata.get("dimension"),
            "messages": request["messages"],
            "temperature": request.get("temperature", 0),
            "options": options,
            "format": _native_format(request),
        })
        if limit and len(prompts) >= limit:
            break
    return prompts


def uncached(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of `messages` with a unique first line. Ollama reuses the KV cache
    for a prompt prefix it has just processed, so replaying the same prompt
    twice (warm-up, --repeat, back-to-back configurations) would skip most of
    prefill and report impossible prefill speeds."""
    first, *rest = messages
    tagged = {**first, "content": f"[benchmark request {uuid4().hex}]\n{first.get('content', '')}"}
    return [tagged, *rest]


def build_native_request(
    prompt: dict[str, Any], model: str, num_ctx: int | None, num_batch: int | None,
    num_thread: int | None = None, output_format: str = "recorded",
) -> dict[str, Any]:
    options: dict[str, Any] = {"temperature": prompt.get("temperature", 0)}
    if (prompt.get("options") or {}).get("num_predict"):
        options["num_predict"] = prompt["options"]["num_predict"]
    if num_ctx:
        options["num_ctx"] = num_ctx
    if num_batch:
        options["num_batch"] = num_batch
    if num_thread:
        options["num_thread"] = num_thread
    body: dict[str, Any] = {
        "model": model,
        "messages": prompt["messages"],
        "stream": False,
        "options": options,
    }
    # "recorded" keeps whatever the app sent (instructor's JSON mode -> "json").
    fmt = prompt.get("format") if output_format == "recorded" else (None if output_format == "none" else output_format)
    if fmt is not None:
        body["format"] = fmt
    return body


def timing_fields(response: dict[str, Any], num_ctx: int | None) -> dict[str, Any]:
    """Ollama's nanosecond timings -> seconds and tokens/second per phase."""
    prompt_tokens = int(response.get("prompt_eval_count") or 0)
    output_tokens = int(response.get("eval_count") or 0)
    prefill_s = (response.get("prompt_eval_duration") or 0) / _NS
    decode_s = (response.get("eval_duration") or 0) / _NS
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": output_tokens,
        "prefill_s": round(prefill_s, 4),
        "decode_s": round(decode_s, 4),
        "load_s": round((response.get("load_duration") or 0) / _NS, 4),
        "total_s": round((response.get("total_duration") or 0) / _NS, 4),
        "prefill_tok_s": round(prompt_tokens / prefill_s, 2) if prefill_s else None,
        "decode_tok_s": round(output_tokens / decode_s, 2) if decode_s else None,
        # Ollama drops the start of an over-long prompt without an error.
        "prompt_truncated": bool(num_ctx and prompt_tokens >= num_ctx * 0.98),
        # "length" = stopped by the answer cap, as /v1's finish_reason reports it.
        "finish_reason": response.get("done_reason"),
    }


async def _replay(
    client: httpx.AsyncClient, base_url: str, body: dict[str, Any], semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        started = datetime.now(UTC).isoformat()
        perf_start = time.perf_counter()
        try:
            response = await client.post(f"{base_url}/api/chat", json=body)
            status = response.status_code
            payload = response.json() if status == 200 else {}
            error = None if status == 200 else response.text[:300]
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: non-JSON body
            status, payload, error = 0, {}, str(exc)
        return {
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_ms": round((time.perf_counter() - perf_start) * 1000, 2),
            "http_status": status,
            "error": error,
            **timing_fields(payload, body["options"].get("num_ctx")),
        }


async def _loaded_model(client: httpx.AsyncClient, base_url: str, model: str) -> dict[str, Any] | None:
    try:
        response = await client.get(f"{base_url}/api/ps")
        response.raise_for_status()
        return find_loaded_model(parse_loaded_models(response.json()), model)
    except httpx.HTTPError:
        return None


async def run_benchmark(args: argparse.Namespace) -> list[dict[str, Any]]:
    source_model = None if args.source_model == "any" else (args.source_model or args.model)
    prompts = load_prompts(Path(args.audit_dir), source_model, args.limit)
    if not prompts:
        sys.exit(
            f"No replayable prompts for model '{source_model}' in {args.audit_dir}. "
            "Run an assessment with that model first, or pass --source-model any."
        )
    # One num_ctx for every request: Ollama reloads the model when it changes.
    num_ctx = args.num_ctx or max((p["options"].get("num_ctx") or 0 for p in prompts), default=0) or None
    num_batch = args.num_batch or None

    def build(prompt: dict[str, Any]) -> dict[str, Any]:
        if not args.allow_cache:
            prompt = {**prompt, "messages": uncached(prompt["messages"])}
        return build_native_request(prompt, args.model, num_ctx, num_batch, args.num_thread, args.format)

    levels = [int(level) for level in args.concurrency.split(",")]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print(
        f"{len(prompts)} prompt(s), num_ctx={num_ctx}, num_batch={num_batch or 'default'}, "
        f"num_thread={args.num_thread or 'default'}, format={args.format}, levels={levels}"
    )
    print("Reminder: the GPU job's OLLAMA_NUM_PARALLEL must be >= the highest level.")

    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        # Warm-up loads the model with this num_ctx so level 1 doesn't pay for it.
        warmup = build(prompts[0])
        await _replay(client, args.base_url, warmup, asyncio.Semaphore(1))

        for level in levels:
            run_id = f"bench-{args.model}-c{level}-{args.label or 'default'}-{stamp}"
            bodies = [build(prompt) for _ in range(args.repeat) for prompt in prompts]
            semaphore = asyncio.Semaphore(level)
            wall_start = time.perf_counter()
            results = await asyncio.gather(*(_replay(client, args.base_url, body, semaphore) for body in bodies))
            wall_s = time.perf_counter() - wall_start
            loaded = await _loaded_model(client, args.base_url, args.model)

            for prompt, result in zip(prompts * args.repeat, results, strict=False):
                rows.append({
                    "run_id": run_id,
                    "source": "gpu_bench",
                    "model": args.model,
                    "dimension": prompt["dimension"],
                    "concurrency": level,
                    "num_ctx": num_ctx,
                    "num_batch": num_batch,
                    "num_thread": args.num_thread,
                    "format": args.format,
                    "label": args.label or "default",
                    "size_vram": loaded["size_vram"] if loaded else None,
                    "offload_ratio": loaded["offload_ratio"] if loaded else None,
                    **result,
                })
            _print_level(level, wall_s, results, loaded)
    return rows


def _print_level(level: int, wall_s: float, results: list[dict[str, Any]], loaded: dict[str, Any] | None) -> None:
    ok = [r for r in results if r["http_status"] == 200]
    output_tokens = sum(r["completion_tokens"] for r in ok)
    prefill = [r["prefill_tok_s"] for r in ok if r["prefill_tok_s"]]
    decode = [r["decode_tok_s"] for r in ok if r["decode_tok_s"]]
    print(
        f"  concurrency {level}: {len(ok)}/{len(results)} ok in {wall_s:.1f}s | "
        f"output {output_tokens / wall_s:.1f} tok/s aggregate | "
        f"prefill median {statistics.median(prefill) if prefill else float('nan'):.0f} tok/s | "
        f"decode median {statistics.median(decode) if decode else float('nan'):.1f} tok/s per request | "
        f"offload {loaded['offload_ratio'] if loaded else 'unknown'}"
    )
    if any(r["prompt_truncated"] for r in ok):
        print("    WARNING: some prompts hit num_ctx and were truncated; raise --num-ctx or use --source-model.")
    if any(r["load_s"] > 1 for r in ok):
        print("    NOTE: some requests paid a model load; options changed or the model was evicted.")


def main() -> None:
    # ai-engine/.env holds the URL the *container* uses; on the host the same
    # tunnel is plain localhost (see evaluation/offline/RUNBOOK.md §0).
    default_base = (
        os.getenv("OLLAMA_BASE_URL", "http://localhost:11435/v1")
        .replace("/v1", "")
        .replace("host.docker.internal", "localhost")
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="Ollama model to benchmark, e.g. sprintsight-llama31")
    parser.add_argument("--base-url", default=default_base, help=f"Ollama server (default {default_base})")
    parser.add_argument("--audit-dir", default="audit_logs", help="Where the app wrote llm_*.txt audit records")
    parser.add_argument("--source-model", help="Replay prompts recorded for this model (default: --model; 'any' for all)")
    parser.add_argument("--limit", type=int, default=12, help="Max unique prompts to replay (default 12)")
    parser.add_argument("--concurrency", default="1", help="Comma-separated levels, e.g. 1,2,4,6")
    parser.add_argument("--repeat", type=int, default=1, help="Passes over the prompt set per level")
    parser.add_argument("--num-ctx", type=int, help="Override num_ctx (default: largest recorded)")
    parser.add_argument("--num-batch", type=int, help="Ollama num_batch for prefill (default: Ollama's)")
    parser.add_argument("--num-thread", type=int, help="Ollama num_thread (CPU threads; default: Ollama's)")
    parser.add_argument(
        "--format", default="recorded",
        help="Output constraint: 'recorded' (what the app sent), 'json', or 'none' (default recorded)",
    )
    parser.add_argument(
        "--allow-cache", action="store_true",
        help="Let Ollama reuse cached prompt prefixes (prefill speeds are then not meaningful)",
    )
    parser.add_argument("--label", help="Name for this configuration; report with --group-by model,label,concurrency")
    parser.add_argument("--timeout", type=float, default=1800, help="Per-request timeout in seconds")
    parser.add_argument("--out", help="Output JSONL (default gpu_logs/bench_<model>_<time>.jsonl)")
    args = parser.parse_args()

    rows = asyncio.run(run_benchmark(args))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = f"_{args.label}" if args.label else ""
    out = Path(args.out or f"gpu_logs/bench_{args.model.replace(':', '_')}{label}_{stamp}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
