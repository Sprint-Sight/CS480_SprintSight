#!/usr/bin/env bash
set -euo pipefail

# ── SprintSight — unified startup ─────────────────────────────────────────────
#
# Launches the WHOLE system with one command:
#   - connects to the GPU on the HPC cluster (via an SSH tunnel), and
#   - brings up both Docker stacks (AI engine + application).
#
# The ONLY manual step is typing your HPC password when prompted.
#
# Usage (run from the repo root, in Git Bash / WSL / macOS / Linux):
#   bash start.sh
#
# Before this works you need, once per work session:
#   1. the SMUResearch VPN connected, and
#   2. a GPU reserved on the cluster (a running Slurm job).
# If a GPU isn't reserved yet, this script stops and explains exactly what to do
# — see "no running Slurm job" guidance printed by hpc/hpc-dev.sh.
# ─────────────────────────────────────────────────────────────────────────────

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI="$ROOT/ai-engine"
BE="$ROOT/backend"
HPC="$AI/hpc/hpc-dev.sh"

echo ""
echo "========================================="
echo "  SprintSight — unified startup"
echo "========================================="

# 1. GPU connection: open the SSH tunnel to the HPC compute node.
#    Prompts for your HPC password, then backgrounds itself. If there's no VPN
#    or no running GPU job, hpc-dev.sh prints step-by-step guidance and exits.
echo ""
echo "[1/4] Connecting to the GPU on the HPC cluster..."
if ! bash "$HPC" tunnel-bg; then
    echo ""
    echo "Startup stopped: the GPU connection could not be established."
    echo "Follow the steps printed above, then run 'bash start.sh' again."
    exit 1
fi

# 2. Ensure the sprintsight-* models exist on the remote Ollama (through the tunnel).
echo ""
echo "[2/4] Ensuring models on the remote Ollama..."
bash "$HPC" models

# 3. AI-engine stack: writes ai-engine/.env for HPC mode, then starts
#    db + mlflow_service + sprintsight_ai (local ollama/model-init stay OFF
#    because the GPU Ollama runs on the cluster). Waits for the healthcheck.
echo ""
echo "[3/4] Starting the AI-engine stack..."
bash "$HPC" docker

# 4. Application stack: frontend + backend + audit-retention + db + minio.
#    Kept as its own Compose project so its 'db'/'postgres_data' never collide
#    with the AI-engine stack's. The two talk over host ports (host.docker.internal).
echo ""
echo "[4/4] Starting the application stack..."
docker compose -p sprintsight-backend -f "$BE/docker-compose.yml" up -d

echo ""
echo "========================================="
echo "  Ready!"
echo "    Frontend : http://localhost:3000"
echo "    Backend  : http://localhost:8000"
echo "    AI engine: http://localhost:8001"
echo "    MLflow   : http://localhost:5000"
echo "    MinIO    : http://localhost:9001"
echo "========================================="
echo ""
echo "Stop everything with:  bash stop.sh"
