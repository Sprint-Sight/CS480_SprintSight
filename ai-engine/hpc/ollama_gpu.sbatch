#!/bin/bash
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16GB
#SBATCH --gres=gpu:1                 # Ollama needs the GPU; the rest of the stack stays local
#SBATCH --time=08:00:00              # Raise this (or resubmit) for longer assessment sessions
#SBATCH --partition=project          # UseMyInfoCommandToCheck
#SBATCH --qos=project                # UseMyInfoCommandToCheck
#SBATCH --job-name=sprintsight-ollama
#SBATCH --output=%u.%j.ollama.out

set -e

# Where CS480_SprintSight was cloned/transferred onto origami
REPO_DIR="${REPO_DIR:-$HOME/CS480_SprintSight}"
MODELS_DIR="$REPO_DIR/ai-engine/models"

# Bind-mounted so pulled/created models persist across job submissions
DATA_DIR="$HOME/sprintsight/ollama_data"
mkdir -p "$DATA_DIR"

echo "Ollama will be reachable on: $(hostname):11434"
echo "From your laptop, open a tunnel through the login node:"
echo "  ssh -L 11434:$(hostname):11434 <netid>@origami.smu.edu.sg"

srun enroot start --rw \
  --env OLLAMA_HOST=0.0.0.0:11434 \
  --mount "$DATA_DIR:/root/.ollama" \
  --mount "$MODELS_DIR:/mnt/models" \
  ollama bash -c '
    set -e
    ollama serve &
    SERVE_PID=$!

    echo "Waiting for Ollama to become ready..."
    until curl -sf http://localhost:11434 >/dev/null; do sleep 2; done

    # alias|base model|Modelfile, mirrors docker-compose.yaml model-init
    MODELS=(
      "sprintsight-llama|llama3.2|Modelfile.llama"
      "sprintsight-qwen|qwen3:8b|Modelfile.qwen"
      "sprintsight-mistral|mistral:7b|Modelfile.mistral"
      "sprintsight-gemma|gemma4:12b|Modelfile.gemma"
    )

    for entry in "${MODELS[@]}"; do
      IFS="|" read -r alias base modelfile <<< "$entry"
      if ! ollama list | grep -q "$alias"; then
        echo "Pulling $base and creating $alias..."
        ollama pull "$base"
        ollama create "$alias" -f "/mnt/models/$modelfile"
      fi
    done

    echo "All SprintSight models ready. Serving until job time limit..."
    wait "$SERVE_PID"
  '
