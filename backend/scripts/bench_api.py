"""API benchmark for NFR 1.2 / 1.3. Read-only, except `queue`, which starts real assessments.

Credentials come from the environment, never the command line (use a faculty test account):
  BENCH_BASE=http://localhost:8000/api/v1  BENCH_EMAIL=...  BENCH_PASSWORD=...

  python backend/scripts/bench_api.py latency --course C --project P --sprint S \
      [--n 300] [--workers 1,8]
      p50/p95/p99 of GET /assessments/reports and /assessments/latest (NFR 1.3: p95 <= 100 ms),
      20 warm-up requests discarded.
  python backend/scripts/bench_api.py queue --course C --project P --sprint S --jobs 3 \
      [--model sprintsight-qwen25-32b]
      POSTs N assessments at once, opens one SSE stream per job and records time to first event,
      worker start and terminal time per job, plus a structural SSE isolation check.
      WARNING: starts N real LLM assessments; not a smoke test.
  python backend/scripts/bench_api.py sample --seconds 1800 --out samples.csv
      Samples host RAM (psutil, if installed), `docker stats` CPU per container and nvidia-smi
      VRAM/util every 2 s. Start it BEFORE the `queue` run and read the peaks afterwards.
"""

import argparse
import concurrent.futures as cf
import csv
import json
import os
import statistics as st
import subprocess
import sys
import time

import httpx

BASE = os.environ.get("BENCH_BASE", "http://localhost:8000/api/v1")
TERMINAL_EVENTS = ("completed", "failed")


def login(client: httpx.Client) -> dict[str, str]:
    credentials = {"email": os.environ["BENCH_EMAIL"], "password": os.environ["BENCH_PASSWORD"]}
    response = client.post(f"{BASE}/auth/login", json=credentials)
    response.raise_for_status()
    token = response.json().get("access_token") or response.json().get("token")
    return {"Authorization": f"Bearer {token}"}


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * len(ordered) + 0.5)) - 1)]


def latency(args: argparse.Namespace) -> None:
    params = {"course_id": args.course, "project_id": args.project, "sprint_id": args.sprint}
    with httpx.Client(timeout=30) as client:
        headers = login(client)
        for path in ("/assessments/reports", "/assessments/latest"):

            def timed_get(_: int, path: str = path) -> tuple[float, int]:
                start = time.perf_counter()
                response = client.get(BASE + path, params=params, headers=headers)
                return (time.perf_counter() - start) * 1000, response.status_code

            for workers in [int(x) for x in args.workers.split(",")]:
                for i in range(20):  # warm-up, discarded
                    timed_get(i)
                with cf.ThreadPoolExecutor(workers) as pool:
                    results = list(pool.map(timed_get, range(args.n)))
                ms = [m for m, status in results if status == 200]
                bad = len(results) - len(ms)
                print(
                    f"{path} workers={workers} n={len(ms)} non200={bad} p50={st.median(ms):.1f} "
                    f"p95={pct(ms, 95):.1f} p99={pct(ms, 99):.1f} max={max(ms):.1f} ms"
                )


def follow(job_id: str, headers: dict[str, str], t0: float) -> dict:
    """Read one job's SSE stream to the end.

    Event payloads carry no job_id, so isolation is checked structurally: the stream must show
    exactly one "started", exactly one terminal event, non-decreasing progress, and its own
    report_id (uniqueness across streams is checked by the caller).
    """
    seen: list[str] = []
    progress: list[float] = []
    first = worker_start = terminal = None
    report_id = None
    url = f"{BASE}/assessments/jobs/{job_id}/events"
    with httpx.Client(timeout=None) as client, client.stream("GET", url, headers=headers) as r:
        event = None
        for line in r.iter_lines():
            now = time.perf_counter() - t0
            if line.startswith("event:"):
                event = line[6:].strip()
                first = now if first is None else first
                seen.append(event)
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                if "progress" in data:
                    progress.append(data["progress"])
                if event == "progress" and worker_start is None:
                    worker_start = now  # the worker has picked the job up
                if event in TERMINAL_EVENTS:
                    terminal = now
                    report_id = data.get("report_id")
    ok = (
        seen.count("started") == 1
        and sum(e in TERMINAL_EVENTS for e in seen) == 1
        and progress == sorted(progress)
    )
    return {
        "job": job_id[:8],
        "first_event_s": first,
        "worker_start_s": worker_start,
        "terminal_s": terminal,
        "events": len(seen),
        "last": seen[-1] if seen else None,
        "report_id": report_id,
        "stream_ok": ok,
    }


def queue(args: argparse.Namespace) -> None:
    with httpx.Client(timeout=30) as client:
        headers = login(client)
    body = {"course_id": args.course, "project_id": args.project, "sprint_id": args.sprint}
    if args.model:
        body["model_name"] = args.model
    t0 = time.perf_counter()
    jobs = []
    with httpx.Client(timeout=30) as client:
        for _ in range(args.jobs):
            r = client.post(f"{BASE}/assessments/assess", json=body, headers=headers)
            if r.status_code != 202:
                sys.exit(f"POST /assessments/assess -> {r.status_code}: {r.text}")
            jobs.append(r.json()["job_id"])
    elapsed = time.perf_counter() - t0
    print("submitted", len(jobs), "jobs in", f"{elapsed:.2f}s (submit must be non-blocking)")
    with cf.ThreadPoolExecutor(len(jobs)) as pool:
        rows = list(pool.map(lambda job_id: follow(job_id, headers, t0), jobs))
    for row in sorted(rows, key=lambda row: row["terminal_s"] or 1e9):
        print(row)
    ids = [row["report_id"] for row in rows if row["report_id"]]
    isolated = all(row["stream_ok"] for row in rows) and len(ids) == len(set(ids))
    print("SSE isolation:", "OK" if isolated else "VIOLATED")


def _run(cmd: list[str]) -> str:
    """stdout of cmd, or "" when the tool is missing on this host (e.g. no nvidia-smi)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def sample(args: argparse.Namespace) -> None:
    try:
        import psutil
    except ImportError:
        psutil = None
        print("psutil not installed: host RAM column will be empty", file=sys.stderr)
    gpu_query = [
        "nvidia-smi",
        "--query-gpu=memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    docker_query = ["docker", "stats", "--no-stream", "--format", "{{.Name}},{{.CPUPerc}}"]
    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["t", "host_ram_used_mb", "container", "cpu_pct", "gpu_mem_used_mb", "gpu_util_pct"]
        )
        end = time.time() + args.seconds
        while time.time() < end:
            ram = round(psutil.virtual_memory().used / 2**20) if psutil else ""
            gpu = [g.strip() for g in _run(gpu_query).strip().split(",")]
            gpu = gpu if len(gpu) == 2 else ["", ""]
            for line in _run(docker_query).split() or [","]:
                name, _, cpu = line.partition(",")
                writer.writerow([round(time.time()), ram, name, cpu.rstrip("%"), *gpu])
            f.flush()
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("latency", "queue"):
        p = sub.add_parser(name)
        for key in ("course", "project", "sprint"):
            p.add_argument(f"--{key}", required=True)
        if name == "latency":
            p.add_argument("--n", type=int, default=300)
            p.add_argument("--workers", default="1,8")
        else:
            p.add_argument("--jobs", type=int, default=3)
            p.add_argument("--model", help="catalogue id, e.g. sprintsight-qwen25-32b")
    p = sub.add_parser("sample")
    p.add_argument("--seconds", type=int, default=600)
    p.add_argument("--out", default="samples.csv")
    args = parser.parse_args()
    {"latency": latency, "queue": queue, "sample": sample}[args.cmd](args)


if __name__ == "__main__":
    main()
