#!/usr/bin/env bash
set -euo pipefail

# ── SprintSight HPC Dev Script ──────────────────────────────────────────────
#
# Automates the HPC-Ollama + local Docker workflow for the team.
#
# Usage (run from ai-engine/):
#   bash hpc/hpc-dev.sh              Full startup: check tunnel, create models, start Docker
#   bash hpc/hpc-dev.sh status       Show cluster job, tunnel, models, Docker, healthcheck
#   bash hpc/hpc-dev.sh models       Create all sprintsight-* aliases on the remote Ollama
#   bash hpc/hpc-dev.sh docker       Start local db + mlflow + sprintsight_ai only
#   bash hpc/hpc-dev.sh submit       SSH to cluster and submit the Slurm GPU job
#   bash hpc/hpc-dev.sh tunnel       Open the SSH tunnel to the running Slurm job's node
#   bash hpc/hpc-dev.sh stop         Tear down Docker and tunnel
#
# Prerequisites:
#   1. SMUResearch VPN connected
#   2. SSH access to the HPC login node (key or password)
#   3. Docker Desktop running
#   4. One-time enroot setup done (see hpc/README.md §2)
#
# Configuration: set variables in ai-engine/.env.hpc or export them.
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_ENGINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env.hpc if it exists (key=value, one per line)
if [[ -f "$AI_ENGINE_DIR/.env.hpc" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$AI_ENGINE_DIR/.env.hpc"
    set +a
fi

# ── Configuration (override via .env.hpc or env vars) ──
HPC_USER="${HPC_USER:-CS480G2}"
HPC_LOGIN_HOST="${HPC_LOGIN_HOST:-10.193.104.102}"
LOCAL_OLLAMA_PORT="${LOCAL_OLLAMA_PORT:-11435}"
REMOTE_OLLAMA_PORT="${REMOTE_OLLAMA_PORT:-11434}"
SLURM_JOB_NAME="${SLURM_JOB_NAME:-sprintsight-ollama}"

OLLAMA_URL="http://localhost:${LOCAL_OLLAMA_PORT}"
MODELS_DIR="$AI_ENGINE_DIR/models"

# ── Detect Python (python3 on Linux/macOS, python on Windows) ──
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "ERROR: Python not found. Install Python 3 and ensure it is on PATH."
    exit 1
fi

# ── Colours ──
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; BLU='\033[0;34m'; NC='\033[0m'
info()  { printf "${BLU}[info]${NC}  %s\n" "$*"; }
ok()    { printf "${GRN}[ ok ]${NC}  %s\n" "$*"; }
warn()  { printf "${YEL}[warn]${NC}  %s\n" "$*"; }
fail()  { printf "${RED}[FAIL]${NC}  %s\n" "$*"; }

# ── Helpers ──────────────────────────────────────────────────────────────────

ssh_hpc() {
    ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
        "${HPC_USER}@${HPC_LOGIN_HOST}" "$@"
}

check_vpn() {
    info "Checking SSH to ${HPC_USER}@${HPC_LOGIN_HOST}..."
    if ssh_hpc "echo ok" >/dev/null 2>&1; then
        ok "HPC login node reachable"
        return 0
    fi
    fail "Cannot reach ${HPC_LOGIN_HOST}. Is the SMUResearch VPN on?"
    return 1
}

get_job_info() {
    ssh_hpc "squeue --me --name=${SLURM_JOB_NAME} --states=RUNNING --noheader -o '%i %N'" 2>/dev/null \
        | head -1 | tr -s ' '
}

check_slurm() {
    info "Checking Slurm job '${SLURM_JOB_NAME}'..."
    local line
    line=$(get_job_info)
    if [[ -n "$line" ]]; then
        local jobid node
        jobid=$(echo "$line" | awk '{print $1}')
        node=$(echo "$line" | awk '{print $2}')
        ok "Job ${jobid} RUNNING on node: ${node}"
        COMPUTE_NODE="$node"
        return 0
    fi
    warn "No running Slurm job named '${SLURM_JOB_NAME}'"
    local pending
    pending=$(ssh_hpc "squeue --me --name=${SLURM_JOB_NAME} --states=PENDING --noheader -o '%i %T'" 2>/dev/null | head -1)
    if [[ -n "$pending" ]]; then
        warn "Job is PENDING: ${pending}"
    fi
    return 1
}

submit_job() {
    check_vpn || return 1
    info "Submitting Slurm GPU job..."
    local out
    out=$(ssh_hpc "sbatch ~/CS480_SprintSight/ai-engine/hpc/ollama_gpu.sbatch" 2>&1)
    echo "  $out"
    if echo "$out" | grep -q "Submitted batch job"; then
        ok "Job submitted — run 'bash hpc/hpc-dev.sh status' once it's RUNNING"
        info "Then open the tunnel: bash hpc/hpc-dev.sh tunnel"
    else
        fail "sbatch failed"
        return 1
    fi
}

check_tunnel() {
    if curl -s --max-time 5 "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        ok "Ollama reachable at localhost:${LOCAL_OLLAMA_PORT}"
        return 0
    fi
    warn "No response on localhost:${LOCAL_OLLAMA_PORT}"
    return 1
}

open_tunnel() {
    check_vpn || return 1
    check_slurm || { fail "Need a running Slurm job first — run: bash hpc/hpc-dev.sh submit"; return 1; }

    info "Opening SSH tunnel: localhost:${LOCAL_OLLAMA_PORT} -> ${COMPUTE_NODE}:${REMOTE_OLLAMA_PORT}"
    echo ""
    echo "  Keep this terminal open. The tunnel stays alive while the SSH session runs."
    echo "  Press Ctrl+C to close the tunnel."
    echo ""
    ssh -N -L "${LOCAL_OLLAMA_PORT}:${COMPUTE_NODE}:${REMOTE_OLLAMA_PORT}" \
        "${HPC_USER}@${HPC_LOGIN_HOST}"
}

list_models() {
    local response
    response=$(curl -s --max-time 10 "${OLLAMA_URL}/api/tags" 2>/dev/null) || {
        echo "  (unreachable)"
        return 0
    }
    if [[ -z "$response" ]]; then
        echo "  (empty response)"
        return 0
    fi
    echo "$response" | $PY -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = data.get('models', [])
    if models:
        for m in models:
            size_gb = m.get('size', 0) / 1e9
            print(f'  {m[\"name\"]:40s} {size_gb:6.1f} GB')
    else:
        print('  (none)')
except Exception as e:
    print(f'  (parse error: {e})')
" || echo "  (python error)"
}

create_model_via_api() {
    local alias="$1" base="$2" modelfile_name="$3"
    local modelfile_path="${MODELS_DIR}/${modelfile_name}"

    if [[ ! -f "$modelfile_path" ]]; then
        fail "Modelfile not found: $modelfile_path"
        return 1
    fi

    # Check if alias already exists
    local existing
    existing=$(curl -s --max-time 10 "${OLLAMA_URL}/api/tags" 2>/dev/null \
        | $PY -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for m in data.get('models', []):
        print(m['name'])
except:
    pass
" 2>/dev/null) || existing=""

    if echo "$existing" | grep -q "^${alias}"; then
        ok "'${alias}' already exists — skipping"
        return 0
    fi

    # Pull base model (idempotent — fast if already present)
    info "Pulling base model '${base}' (may take several minutes on first run)..."
    # Use Python for the pull request so streaming/JSON parsing works reliably on Windows
    $PY -c "
import json, sys, urllib.request

url = sys.argv[1] + '/api/pull'
data = json.dumps({'name': sys.argv[2]}).encode()
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req, timeout=1800) as resp:
        for raw in resp:
            try:
                d = json.loads(raw)
                st = d.get('status', '')
                if st:
                    print(f'  {st}', flush=True)
            except json.JSONDecodeError:
                pass
except Exception as e:
    print(f'  Error pulling model: {e}', file=sys.stderr)
    sys.exit(1)
" "$OLLAMA_URL" "$base"

    # Create alias from Modelfile
    info "Creating '${alias}' from ${modelfile_name}..."
    $PY -c "
import json, sys, urllib.request

with open(sys.argv[1]) as f:
    mf = f.read()

data = json.dumps({'name': sys.argv[2], 'modelfile': mf}).encode()
req = urllib.request.Request(
    sys.argv[3] + '/api/create',
    data=data,
    headers={'Content-Type': 'application/json'},
)

try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            try:
                d = json.loads(raw)
                st = d.get('status', '')
                if st:
                    print(f'  {st}', flush=True)
            except json.JSONDecodeError:
                pass
except Exception as e:
    print(f'  Error creating model: {e}', file=sys.stderr)
    sys.exit(1)
" "$modelfile_path" "$alias" "$OLLAMA_URL"

    ok "'${alias}' created"
}

ensure_models() {
    check_tunnel || { fail "Tunnel not open — run: bash hpc/hpc-dev.sh tunnel (in another terminal)"; return 1; }

    info "Ensuring all SprintSight models exist on remote Ollama..."
    echo ""
    create_model_via_api "sprintsight-llama"   "llama3.2"    "Modelfile.llama"
    create_model_via_api "sprintsight-qwen"    "qwen3:8b"    "Modelfile.qwen"
    create_model_via_api "sprintsight-mistral" "mistral:7b"  "Modelfile.mistral"
    create_model_via_api "sprintsight-gemma"   "gemma4:12b"  "Modelfile.gemma"
    echo ""
    info "Remote models:"
    list_models
}

write_hpc_env() {
    local env_file="$AI_ENGINE_DIR/.env"
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "${env_file}.bak"
        info "Backed up existing .env to .env.bak"
    fi
    cat > "$env_file" <<EOF
# Generated by hpc-dev.sh — HPC mode (Ollama via SSH tunnel on port ${LOCAL_OLLAMA_PORT})
OLLAMA_BASE_URL=http://host.docker.internal:${LOCAL_OLLAMA_PORT}/v1
LOG_BUNDLE_DISPLAY=true
EOF
    ok ".env written for HPC mode (port ${LOCAL_OLLAMA_PORT})"
}

start_docker() {
    cd "$AI_ENGINE_DIR"
    write_hpc_env

    info "Starting db + mlflow_service..."
    docker compose up -d db mlflow_service

    info "Building and starting sprintsight_ai (skipping ollama/model-init)..."
    docker compose up -d --no-deps --build sprintsight_ai

    info "Waiting for healthcheck..."
    local attempts=0
    while [[ $attempts -lt 20 ]]; do
        sleep 3
        local resp
        resp=$(curl -s --max-time 5 http://localhost:8001/health 2>/dev/null) || resp=""
        if [[ -n "$resp" ]]; then
            local st
            st=$(echo "$resp" | $PY -c "
import sys, json
try:
    print(json.loads(sys.stdin.read()).get('status',''))
except:
    print('')
" 2>/dev/null) || st=""
            case "$st" in
                ok)       ok "Healthcheck: OK"; return 0 ;;
                degraded) warn "Healthcheck: DEGRADED — models may still be loading"
                          echo "$resp" | $PY -m json.tool 2>/dev/null || echo "$resp"
                          return 0 ;;
            esac
        fi
        ((attempts++))
    done
    fail "sprintsight_ai not responding after 60 s"
    return 1
}

show_status() {
    echo ""
    echo "========================================="
    echo "  SprintSight HPC Dev -- Status"
    echo "========================================="
    echo ""

    # SSH
    check_vpn 2>/dev/null || true

    # Slurm
    check_slurm 2>/dev/null || true

    # Tunnel
    echo ""
    check_tunnel 2>/dev/null || true

    # Models
    if check_tunnel >/dev/null 2>&1; then
        info "Remote Ollama models:"
        list_models
    fi

    # Docker
    echo ""
    info "Local Docker services:"
    cd "$AI_ENGINE_DIR"
    docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || echo "  (not running)"

    # Health
    echo ""
    local resp
    resp=$(curl -s --max-time 5 http://localhost:8001/health 2>/dev/null) || resp=""
    if [[ -n "$resp" ]]; then
        info "Healthcheck:"
        echo "$resp" | $PY -m json.tool 2>/dev/null || echo "  $resp"
    else
        warn "sprintsight_ai not responding on localhost:8001"
    fi
    echo ""
}

stop_all() {
    cd "$AI_ENGINE_DIR"
    info "Stopping Docker services..."
    docker compose down 2>/dev/null || true
    ok "Docker stopped"
    echo ""
    info "To close the SSH tunnel, press Ctrl+C in the tunnel terminal."
}

# ── Main ─────────────────────────────────────────────────────────────────────

cmd="${1:-full}"

case "$cmd" in
    full)
        echo ""
        echo "========================================="
        echo "  SprintSight HPC Dev -- Full Startup"
        echo "========================================="
        echo ""
        info "Step 1/3: Verify tunnel"
        if ! check_tunnel; then
            echo ""
            fail "SSH tunnel not open on localhost:${LOCAL_OLLAMA_PORT}."
            echo ""
            echo "  Open it in a separate terminal:"
            echo ""
            echo "    bash hpc/hpc-dev.sh tunnel"
            echo ""
            echo "  Or manually:"
            echo "    ssh -L ${LOCAL_OLLAMA_PORT}:<node>:${REMOTE_OLLAMA_PORT} ${HPC_USER}@${HPC_LOGIN_HOST}"
            echo ""
            exit 1
        fi

        echo ""
        info "Step 2/3: Ensure models"
        ensure_models

        echo ""
        info "Step 3/3: Start Docker"
        start_docker

        echo ""
        echo "========================================="
        ok "Ready! API: http://localhost:8001"
        ok "MLflow: http://localhost:5000"
        echo "========================================="
        ;;

    status)  show_status ;;
    models)  ensure_models ;;
    docker)  start_docker ;;
    submit)  submit_job ;;
    tunnel)  open_tunnel ;;
    stop)    stop_all ;;
    *)
        echo "Usage: bash hpc/hpc-dev.sh {full|status|models|docker|submit|tunnel|stop}"
        echo ""
        echo "Commands:"
        echo "  full     Check tunnel, create models, start Docker (default)"
        echo "  status   Show cluster job, tunnel, models, Docker health"
        echo "  models   Create/verify sprintsight-* models on remote Ollama"
        echo "  docker   Start local db + mlflow + sprintsight_ai"
        echo "  submit   Submit the Slurm GPU job on the cluster"
        echo "  tunnel   Open SSH tunnel to the Slurm job's compute node"
        echo "  stop     Stop Docker and show tunnel teardown instructions"
        exit 1
        ;;
esac
