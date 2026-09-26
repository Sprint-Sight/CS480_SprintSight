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
   ollama rm sprintsight-llama
   ollama create sprintsight-llama -f /mnt/models/Modelfile.llama
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
