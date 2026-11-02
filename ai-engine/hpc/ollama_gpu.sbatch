#!/bin/bash
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16GB
#SBATCH --gres=gpu:1                 # Ollama needs the GPU; the rest of the stack stays local
#SBATCH --time=08:00:00              # Raise this (or resubmit) for longer assessment sessions
#SBATCH --partition=project          # UseMyInfoCommandToCheck
#SBATCH --qos=cs480qos               # UseMyInfoCommandToCheck
#SBATCH --job-name=sprintsight-ollama
# Absolute path: %u.%j.ollama.out (relative) lands wherever `sbatch` was run from, not here.
# Create the directory once: mkdir -p ~/slurm-logs
#SBATCH --output=/common/home/projectgrps/CS480/CS480G2/slurm-logs/%u.%j.ollama.out

set -e

# Where CS480_SprintSight was cloned/transferred onto origami
REPO_DIR="${REPO_DIR:-$HOME/CS480_SprintSight}"
MODELS_DIR="$REPO_DIR/ai-engine/models"

# Bind-mounted so pulled/created models persist across job submissions
DATA_DIR="$HOME/sprintsight/ollama_data"
mkdir -p "$DATA_DIR"

# Ollama server settings. sbatch exports the submitting shell's environment,
# so override any of these per job, e.g.
#   OLLAMA_NUM_PARALLEL=4 OLLAMA_KV_CACHE_TYPE=q8_0 sbatch ollama_gpu.sbatch
# (hpc-dev.sh submit forwards them from your laptop). NUM_PARALLEL is how many
# requests one loaded model decodes at once; the KV cache grows with
# num_ctx x NUM_PARALLEL, so the 32B models only fit 1 at 16K context.
OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-1}"
OLLAMA_KV_CACHE_TYPE="${OLLAMA_KV_CACHE_TYPE:-q4_0}"
# Ollama's default 5-minute idle unload makes the next call pay a full model
# load; keep the model resident across a session's assessment runs.
OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-30m}"
# CPU threads per request, baked into each model by ollama-entrypoint.sh.
# Matches the CPUs this job reserves; Ollama's own default counts the whole
# node's cores and the threads then contend for these few CPUs.
OLLAMA_MODEL_NUM_THREAD="${OLLAMA_MODEL_NUM_THREAD:-${SLURM_CPUS_PER_TASK:-4}}"

# ── GPU telemetry ────────────────────────────────────────────────────────────
# One nvidia-smi sample per second for the whole job, on the same node and
# clock as Ollama. research/gpu_report.py joins it with the AI engine's
# request markers; fetch it to your laptop with `bash hpc/hpc-dev.sh gpu-logs`.
GPU_LOG_DIR="$HOME/sprintsight/gpu-logs"
mkdir -p "$GPU_LOG_DIR"
GPU_LOG="$GPU_LOG_DIR/${SLURM_JOB_ID}.gpu.csv"
GPU_SAMPLE_MS="${GPU_SAMPLE_MS:-1000}"

# Hardware fingerprint: Slurm can hand a resubmitted job a different GPU model,
# and benchmarks are only comparable on the same one.
nvidia-smi --query-gpu=name,driver_version,memory.total,power.limit --format=csv \
  > "$GPU_LOG_DIR/${SLURM_JOB_ID}.gpu-info.csv" \
  || echo "WARNING: nvidia-smi is not visible from the batch step; no GPU telemetry for this job."

GPU_FIELDS="timestamp,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.sm,temperature.gpu"
# Throttle reasons were renamed clocks_event_reasons in newer drivers; use
# whichever name this driver accepts, and sample without it otherwise.
for field in clocks_throttle_reasons.active clocks_event_reasons.active; do
  if nvidia-smi --query-gpu="$field" --format=csv,noheader >/dev/null 2>&1; then
    GPU_FIELDS="$GPU_FIELDS,$field"
    break
  fi
done

# TZ=UTC: nvidia-smi stamps samples in local time with no zone; the AI
# engine's request markers are UTC.
TZ=UTC nvidia-smi --query-gpu="$GPU_FIELDS" --format=csv,nounits -lms "$GPU_SAMPLE_MS" > "$GPU_LOG" 2>/dev/null &
SAMPLER_PID=$!
trap 'kill "$SAMPLER_PID" 2>/dev/null || true' EXIT

echo "Ollama will be reachable on: $(hostname):11434"
echo "From your laptop, open a tunnel through the login node:"
echo "  ssh -L 11434:$(hostname):11434 <netid>@origami.smu.edu.sg"
echo "Ollama settings: NUM_PARALLEL=$OLLAMA_NUM_PARALLEL KV_CACHE_TYPE=$OLLAMA_KV_CACHE_TYPE KEEP_ALIVE=$OLLAMA_KEEP_ALIVE MODEL_NUM_THREAD=$OLLAMA_MODEL_NUM_THREAD"
echo "GPU telemetry: $GPU_LOG (every ${GPU_SAMPLE_MS} ms)"

srun enroot start --rw \
  --rc "$REPO_DIR/ai-engine/hpc/ollama-entrypoint.sh" \
  --env OLLAMA_HOST=0.0.0.0:11434 \
  --env OLLAMA_MODELS=/root/.ollama/models \
  --env OLLAMA_FLASH_ATTENTION=1 \
  --env OLLAMA_KV_CACHE_TYPE="$OLLAMA_KV_CACHE_TYPE" \
  --env OLLAMA_NUM_PARALLEL="$OLLAMA_NUM_PARALLEL" \
  --env OLLAMA_KEEP_ALIVE="$OLLAMA_KEEP_ALIVE" \
  --env OLLAMA_MODEL_NUM_THREAD="$OLLAMA_MODEL_NUM_THREAD" \
  --mount "$DATA_DIR:/root/.ollama" \
  --mount "$MODELS_DIR:/mnt/models" \
  ollama
