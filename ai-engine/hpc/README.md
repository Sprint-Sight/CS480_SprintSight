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
