# Running Ollama on the Origami GPU cluster

This runs **only** the `ollama` service on Origami's GPU via Slurm/enroot.
`db`, `mlflow_service`, and `sprintsight_ai` keep running in your local
`docker compose` stack as before; they just point at the remote Ollama
instead of the local one.

Origami's compute nodes don't support `docker compose` — jobs run single
containers via `enroot` (see https://violet.scis.dev/docs/Advanced%20settings/containers).
Docker/Compose only exist on the login node for convenience, not for running
GPU workloads.

## 1. Get the repo onto origami

Transfer or clone `CS480_SprintSight` into your home directory on origami
(see the cluster's "Transfer Files" docs), e.g.:

```bash
git clone <your-repo-url> ~/CS480_SprintSight
```

## 2. One-time enroot setup

From the origami login node:

```bash
mkdir -p ~/slurm-logs   # matches the absolute --output path in ollama_gpu.sbatch
cd ~/CS480_SprintSight/ai-engine/hpc
bash setup_ollama_container.sh
```

Check your actual `--partition`/`--qos` with `myinfo` and edit
`setup_ollama_container.sh` / `ollama_gpu.sbatch` if they differ from
`project`.

## 3. Submit the GPU job

```bash
sbatch ~/CS480_SprintSight/ai-engine/hpc/ollama_gpu.sbatch
squeue --me
```

The job pulls/creates the four `sprintsight-*` models (skipped if already
present in `~/sprintsight/ollama_data`, which persists across job runs) and
then serves Ollama until the `--time` limit. Check `<netid>.<jobid>.ollama.out`
for the compute node's hostname, or read it from `squeue --me`.

## 4. Tunnel from your laptop

```bash
ssh -L 11434:<compute-node-hostname>:11434 <netid>@origami.smu.edu.sg
```

Keep this connection open while you use the AI engine.

## 5. Point your local stack at the tunnel

In `ai-engine/.env`:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

Then start the stack **without** the local `ollama`/`model-init` services:

```powershell
cd ai-engine
docker compose up -d db mlflow_service
docker compose up -d --no-deps --build sprintsight_ai
```

`--no-deps` stops Compose from also trying to start `ollama`/`model-init`
locally. Verify with:

```powershell
curl.exe http://localhost:8001/health
```

## Notes

- Community `project`/`student` queues can be pre-empted; a long-running
  Ollama job may be killed early. Re-run `sbatch` if that happens — models
  are already cached in `~/sprintsight/ollama_data`.
- To switch back to a fully local stack, revert `OLLAMA_BASE_URL` and run
  `docker compose up -d --build sprintsight_ai` (with its normal deps).

## Command reference (origami)

| Task | Command |
|---|---|
| Check your partition/qos/account | `myinfo` |
| Submit the Ollama job | `sbatch ollama_gpu.sbatch` |
| List your queued/running jobs | `squeue --me` |
| Job details (node, state, time left) | `scontrol show job <jobid>` |
| Cancel a job | `scancel <jobid>` |
| Cancel all your jobs | `scancel --me` |
| Tail live job output | `tail -f <netid>.<jobid>.ollama.out` |
| View full job output | `cat <netid>.<jobid>.ollama.out` |
| List your enroot containers | `enroot list` |
| Remove an enroot container | `enroot remove ollama` |
| Re-import the image (after removing) | `srun --partition=project --qos=cs480qos --mem=4G --cpus-per-task=4 enroot import docker://ollama/ollama:latest` |
| Interactive shell inside the container (debug) | `srun --pty --partition=project --qos=cs480qos --mem=8G --cpus-per-task=4 --gres=gpu:1 enroot start --rw --mount ~/sprintsight/ollama_data:/root/.ollama ollama sh` |
| Check GPU is visible on a compute node | (inside the interactive shell above) `nvidia-smi` |
| Disk/quota usage in home dir | `du -sh ~/* | sort -h` or `quota -s` |

## Command reference (local machine)

| Task | Command |
|---|---|
| Open the tunnel to the GPU node | `ssh -L 11434:<node>:11434 <netid>@origami.smu.edu.sg` |
| Start db + mlflow only | `docker compose up -d db mlflow_service` |
| (Re)build and start FastAPI against remote Ollama | `docker compose up -d --no-deps --build sprintsight_ai` |
| Tail FastAPI logs | `docker compose logs -f sprintsight_ai` |
| Health check | `curl.exe http://localhost:8001/health` |
| Stop everything | `docker compose down` |

## Syncing script changes to origami

```bash
# on origami
cd ~/CS480_SprintSight
git pull
chmod +x ai-engine/hpc/*.sh
```

If `git pull` complains about an untracked file it would overwrite (e.g. a
one-off copy you `cat >`'d by hand), remove your

## Timing an assessment run

- **Live logs**: `docker compose logs -f sprintsight_ai` — `evaluator.py` logs
  each dimension's duration (`Completed rubric dimension '...' ... in %.2f
  seconds`) and the total run time (`Evaluation by model ... completed in
  %.2f seconds`).
- **MLflow UI** (`http://localhost:5000`): the `Evaluate_Complete_Sprint`
  trace and its child spans show per-call latency.
- **Audit logs** (`ai-engine/audit_logs/*.txt`): each record includes a
  `duration_ms` field for the raw Ollama request.

## Tuning `num_ctx` for larger repositories

> **Warning (verified 2026-11-02, Ollama 0.34.4):** the app calls Ollama's
> OpenAI-compatible `/v1` endpoint, which **ignores** `options`. A `/v1` request
> with `options.num_ctx=1024` kept the model's 40960 context and an
> untruncated prompt; the native `/api/chat` endpoint applied it. So the
> context actually used is the Modelfile's `PARAMETER num_ctx` (capped at the
> model's own maximum, e.g. 40960 for qwen3:8b). The request-parameter route
> below has no effect until the client changes endpoint. Change the Modelfile
> instead; the GPU job recreates the models from the Modelfiles at every start.

No enroot/GPU job changes are needed for this — `num_ctx` is sent as a
runtime request parameter to Ollama (`options.num_ctx` in
`llm_client._request_extra_body`), not something baked into the container or
job script. It's only bounded by the compute node's available VRAM (RTX 3090
= 24 GiB here).

**Quick manual adjustment (no cluster changes at all):**

1. Edit the ceiling in `ai-engine/schemas/modelname.py`:
   ```python
   MODEL_NUM_CTX: dict[str, int] = {
       ModelName.SPRINTSIGHT_LLAMA.value: 65536,  # raised from 49152
       ...
   }
   ```
2. Restart the FastAPI container to pick up the code change:
   ```powershell
   docker compose up -d --no-deps --build sprintsight_ai
   ```
3. Run an assessment and check `docker compose logs -f sprintsight_ai` — if
   the GPU can't fit the requested context, Ollama's error will show up there
   (or via `ollama ps` on the cluster node, which shows the currently loaded
   context size).

**Optional — keep the Modelfile default in sync** (only matters if you ever
query the model directly, e.g. via `ollama run`, without going through
`llm_client.py`'s explicit override):

1. Bump `PARAMETER num_ctx` in the relevant `ai-engine/models/Modelfile.<name>`.
2. Recreate the model on the cluster so the new default takes effect — the
   job's `ollama-entrypoint.sh` only creates a model if the alias doesn't
   exist yet, so force it manually inside the running container:
   ```bash
   srun --pty --partition=project --qos=cs480qos --mem=8G --cpus-per-task=4 \
     --gres=gpu:1 --jobid=<jobid> \
     enroot start --rw --mount ~/sprintsight/ollama_data:/root/.ollama \
     --mount ~/CS480_SprintSight/ai-engine/models:/mnt/models ollama sh
   # inside the container:
   ollama rm sprintsight-qwen
   ollama create sprintsight-qwen -f /mnt/models/Modelfile.qwen
   ```

`LLM_NUM_CTX_FLOOR` (env var on `sprintsight_ai`) only ever *shrinks* the
per-run context below this ceiling for small bundles; it can't exceed it.

### How to find your actual ceiling

Ollama already estimates a safe default from available VRAM at startup —
visible in your own job log:
```
msg="vram-based default context" total_vram="23.6 GiB" default_num_ctx=32768
```
That's a conservative baseline for whatever model it considered first.
Anything configured above it (we already push to 49152) isn't pre-validated
— it either loads or OOMs, so treat this as a starting point, not a limit.

**1. Rough formula (sanity check before testing):**

```
KV cache bytes ≈ 2 × num_ctx × num_layers × hidden_size × bytes_per_element
VRAM budget    ≈ 24 GiB (RTX 3090) − model weight size (`ollama ps`) − ~1 GiB overhead
```

- `bytes_per_element` = 2 for the default fp16 KV cache, or 1 for `q8_0`
- Get `num_layers`/`hidden_size` from `ollama show <model> --modelfile` (or
  `embedding_length` in `ollama list -v` / `api/show`)
- This overestimates for GQA models (fewer KV heads than full hidden size),
  so treat the result as a conservative lower bound, not exact.

**2. Empirical (authoritative) — binary search on the actual GPU:**

```bash
# open an interactive shell in the running job's container
srun --pty --partition=project --qos=cs480qos --mem=8G --cpus-per-task=4 \
  --gres=gpu:1 --jobid=<jobid> \
  enroot start --rw --mount ~/sprintsight/ollama_data:/root/.ollama ollama sh
```
Inside, load the model at increasing `num_ctx` values (e.g. via a `curl`-free
request with `ollama run <model> --verbose`, or by hitting the API through
`sprintsight_ai`) while watching:
- `ollama ps` — shows the currently loaded model's VRAM size
- `nvidia-smi` — actual GPU memory usage on the node

Step up (32768 → 49152 → 65536 → 81920 → ...) until Ollama errors on load or
`nvidia-smi` nears 24 GiB, then back off ~10–15% for safety margin. `--gres=gpu:1`
gives your job exclusive use of the GPU, so no other jobs compete for VRAM
while yours is running.

**3. Free up headroom without lowering `num_ctx`:** set
`OLLAMA_KV_CACHE_TYPE=q8_0` in `ollama_gpu.sbatch`'s `--env` list — this
roughly halves KV cache size at a small quality cost. local copy first:
`rm ai-engine/hpc/<file>` then `git pull` again.

## Measuring GPU utilisation

Every GPU job now records telemetry, and every assessment records request
timings, so you can show how hard each model drives the GPU and where it
sits idle. Nothing needs switching on.

**What gets recorded**

| Where | What | Written by |
|---|---|---|
| `~/sprintsight/gpu-logs/<jobid>.gpu.csv` (cluster) | `nvidia-smi` every second: utilisation, memory-bus utilisation, VRAM, power, SM clock, temperature, clock-slowdown reasons. Timestamps in UTC | `ollama_gpu.sbatch` |
| `~/sprintsight/gpu-logs/<jobid>.gpu-info.csv` | GPU name, driver, VRAM, power limit | `ollama_gpu.sbatch` |
| `ai-engine/audit_logs/request_markers.jsonl` | One line per Ollama request: UTC start/end, model, dimension, MLflow run ID, concurrency, token counts | `services/llm_client.py` |
| MLflow run of each assessment | `gpu_offload_ratio` (share of the model in VRAM; below 1 means some layers on the CPU), `gpu/ollama_ps.json`, `dimension_concurrency` param | `services/evaluator.py` |

**Settings you can sweep**

| Setting | Where | Default | Notes |
|---|---|---|---|
| `OLLAMA_NUM_PARALLEL` | GPU job (`.env.hpc`, forwarded by `hpc-dev.sh submit`) | 1 | Requests one loaded model decodes together. KV cache grows with `num_ctx` × this; the 32B models fit 1 at 16K |
| `LLM_DIMENSION_CONCURRENCY` | `ai-engine/.env` | 1 | Dimensions the engine sends at once. Keep equal to `OLLAMA_NUM_PARALLEL` |
| `OLLAMA_KV_CACHE_TYPE` | GPU job | q4_0 | `f16`/`q8_0` cost more VRAM but less quality loss; the 8B models have room |
| `OLLAMA_MODEL_NUM_THREAD` | GPU job | the job's `--cpus-per-task` (4) | CPU threads per request, baked into every model by `ollama-entrypoint.sh` at job start (the app's `/v1` requests can't set it). Without it, Ollama sizes threads from the whole node and they contend for the job's 4 CPUs on every token: on qwen3-8b, decoding was ~3.5× slower (17 vs 60 tok/s) with GPU utilisation near 30% |
| `num_batch` | `gpu_bench --num-batch` only | Ollama's 512 | Prefill batch size. Can be measured with the benchmark (native API); to use it in the app it would have to go in the Modelfiles |
| `OLLAMA_KEEP_ALIVE` | GPU job | 30m | How long an idle model stays loaded |
| `HPC_GPU_TYPE` | `.env.hpc` | unset | Pins the GPU model (`sinfo -o "%N %G"` lists types) so runs are comparable |

Server settings (`OLLAMA_*`) only change when the job restarts:
`scancel --me`, then `hpc-dev.sh submit` again.

**Procedure for one model**

```bash
# 1. GPU job with the settings under test (example: 4 parallel slots)
OLLAMA_NUM_PARALLEL=4 bash hpc/hpc-dev.sh submit
bash hpc/hpc-dev.sh status                    # wait for RUNNING
bash start.sh                                 # from the repo root

# 2. Real assessments: set LLM_DIMENSION_CONCURRENCY=4 in ai-engine/.env,
#    restart sprintsight_ai, run assessments for the model from the app.
#    And/or a controlled sweep replaying the recorded prompts:
python -m research.gpu_bench --model sprintsight-llama31 --concurrency 1,2,4

# 3. Fetch the telemetry and build the report
bash hpc/hpc-dev.sh gpu-logs                  # -> gpu_logs/<jobid>.gpu.csv + clock offset
python -m research.gpu_report --gpu-csv gpu_logs/<jobid>.gpu.csv \
    --markers audit_logs/request_markers.jsonl gpu_logs/bench_*.jsonl --mlflow
```

The report writes `summary.md`/`summary.csv` and a timeline plot per
(model, concurrency) into `gpu_logs/report_<time>/`. With `--mlflow`, it logs
one run per group in the `sprintsight_gpu_utilisation` experiment.

**Reading the numbers**

- `util_busy_mean`: GPU utilisation while a request was running.
  `util_window_mean` includes the gaps between requests. A big difference
  between them means the GPU waits on the client, not that it is weak.
- `idle_gap_fraction`: share of a run with no request in flight. Raising
  concurrency is what shrinks it.
- `utilization.gpu` is the share of time *any* kernel ran, not how much of
  the chip was used. Judge saturation by throughput: `output_tok_s` should
  stop rising as concurrency goes up (the knee), or VRAM should be near full.
- `decode_bw_eff` (sweep rows only): decode speed per request against the
  card's memory-bandwidth ceiling. Single-stream decode is limited by memory
  bandwidth, so this, not `util`, says how close one request is to the limit.
- `offload_ratio_min` / `gpu_offload_ratio` below 1: the model doesn't fit;
  results from that run are not representative.
- `throttled_fraction` above 0: thermal or hardware limits held the clocks down.
- `power_cap_fraction`: the driver's software power-cap flag. This RTX 3090
  sets it even when idle at ~28 W, so it only means something together with
  `power_busy_pct` near 100% and a lower `sm_clock_busy_median_mhz`. That
  combination means the card is at its power limit, i.e. fully used.
- `unanswered_requests` / `unanswered_s`: requests that got no response
  before the client timeout. Ollama keeps generating until the client gives
  up, so this is GPU time spent on output that was thrown away. Before the
  answer cap (`LLM_MAX_OUTPUT_TOKENS`, default 8192), llama3.1 and mistral
  each ran 20-minute runaway answers at full power.
- `length_capped`: answers stopped by `LLM_MAX_OUTPUT_TOKENS` (runaway output
  cut off instead of running for 20 minutes). `instructor` doesn't re-ask an
  incomplete answer, so the engine re-asks it `LLM_LENGTH_REASKS` times (default
  1) with a "reply concisely" note. If the dimension still fails, the engine
  log shows `failed after`.
- `truncated_prompts`: prompts Ollama cut to fit the model's context, so the
  grade saw partial evidence. Any non-zero value is a grading problem, not just
  a performance one. Each model's tokenizer density is in
  `MODEL_CHARS_PER_TOKEN` (`schemas/modelname.py`, measured), and the prompt
  budget uses it so prompts fit the real context.
- Benchmark runs add a unique first line to every prompt so Ollama can't reuse
  a cached prompt; `--allow-cache` turns this off, but prefill speeds are then
  meaningless.
- Compare configurations by giving each `gpu_bench` run a `--label`, then
  report with `--group-by model,label`.
- Cross-check the same time window on the cluster's own dashboard:
  https://green.smu.edu.sg/gpustats (SMU network/VPN; node → GPU → time range).

**Before using a faster setting for grading:** batched decoding isn't
guaranteed bit-identical to one request at a time. Re-run the same sprint with
the old and the new setting, then compare the two runs:

```bash
python -m research.compare_runs --list                 # find the run IDs
python -m research.compare_runs <old-run> <new-run>    # exits 1 if any score changed
```

It compares each dimension's raw model answer, retries included, and reports:
- whether the evidence was the same
- whether the answers are byte-identical
- the scores
- citation overlap and justification similarity where the answers differ

A change that only affects speed (such as the CPU thread count) should come
out **IDENTICAL**: on qwen3-8b, the 4-thread fix cut 689 s to 188 s with every
answer byte-for-byte unchanged.
