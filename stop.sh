#!/usr/bin/env bash
set -uo pipefail

# ── SprintSight — unified teardown ────────────────────────────────────────────
# Stops both Docker stacks and closes the background SSH tunnel to the GPU.
# (It does NOT cancel your Slurm GPU job — that keeps running on the cluster so
#  you can start again quickly. To release the GPU, cancel the job on the
#  cluster: bash ai-engine/hpc/hpc-dev.sh status  shows its job id.)
#
# Usage:  bash stop.sh
# ─────────────────────────────────────────────────────────────────────────────

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI="$ROOT/ai-engine"
BE="$ROOT/backend"

echo "Stopping the application stack..."
docker compose -p backend -f "$BE/docker-compose.yml" down

echo "Stopping the AI-engine stack..."
bash "$AI/hpc/hpc-dev.sh" stop

# Close the backgrounded `ssh -f -N -L <localport>:<node>:11434` tunnel.
# Read the local port from .env.hpc so a custom LOCAL_OLLAMA_PORT still matches.
LOCAL_OLLAMA_PORT="11435"
if [[ -f "$AI/.env.hpc" ]]; then
    # shellcheck disable=SC1090
    port_line="$(grep -E '^LOCAL_OLLAMA_PORT=' "$AI/.env.hpc" | tail -1 | cut -d= -f2)"
    [[ -n "${port_line:-}" ]] && LOCAL_OLLAMA_PORT="$port_line"
fi
echo "Closing the SSH tunnel on localhost:${LOCAL_OLLAMA_PORT}..."
pkill -f "ssh -f -N.*-L ${LOCAL_OLLAMA_PORT}:" 2>/dev/null \
    && echo "  Tunnel closed." \
    || echo "  No background tunnel found (already closed?)."

echo "Done."
