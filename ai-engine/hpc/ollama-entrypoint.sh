#!/bin/sh
# enroot --rc entrypoint: no bash/curl in the ollama image, keep this POSIX sh.
set -e

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama to become ready..."
until ollama list >/dev/null 2>&1; do
  sleep 2
done

# CPU threads each model uses per request, from the job's --cpus-per-task
# (ollama_gpu.sbatch). The app calls Ollama's OpenAI-compatible /v1 endpoint,
# which ignores per-request options, so this has to be baked into the model.
# Unset, Ollama sizes threads from the whole node rather than the job's CPUs,
# and they contend on every token (measured: ~3.5x slower decoding).
MODEL_NUM_THREAD="${OLLAMA_MODEL_NUM_THREAD:-}"

# alias|base model|Modelfile, mirrors docker-compose.yaml model-init
for entry in \
  "sprintsight-qwen|qwen3:8b|Modelfile.qwen" \
  "sprintsight-mistral|mistral:7b|Modelfile.mistral" \
  "sprintsight-gemma|gemma4:12b|Modelfile.gemma" \
  "sprintsight-judge-phi|phi4:14b|Modelfile.phi" \
  "sprintsight-llama31|llama3.1:8b|Modelfile.llama31" \
  "sprintsight-qwen25-32b|qwen2.5:32b|Modelfile.qwen25-32b" \
  "sprintsight-r1-32b|deepseek-r1:32b|Modelfile.deepseek-r1" \
  "sprintsight-coder-32b|qwen2.5-coder:32b|Modelfile.qwen25-coder"
do
  alias=$(echo "$entry" | cut -d'|' -f1)
  base=$(echo "$entry" | cut -d'|' -f2)
  modelfile=$(echo "$entry" | cut -d'|' -f3)
  if ! ollama list | grep -q "^$base[[:space:]]"; then
    echo "Pulling $base..."
    ollama pull "$base"
  fi
  # Recreated every job (seconds; the base weights are reused) so aliases
  # always match the current Modelfiles and thread count.
  source_file="/mnt/models/$modelfile"
  if [ -n "$MODEL_NUM_THREAD" ]; then
    { cat "$source_file"; printf '\nPARAMETER num_thread %s\n' "$MODEL_NUM_THREAD"; } > "/tmp/$modelfile"
    source_file="/tmp/$modelfile"
  fi
  echo "Creating $alias (num_thread=${MODEL_NUM_THREAD:-ollama default})..."
  ollama create "$alias" -f "$source_file" >/dev/null
done

echo "All SprintSight models ready. Serving until job time limit..."
wait "$SERVE_PID"
