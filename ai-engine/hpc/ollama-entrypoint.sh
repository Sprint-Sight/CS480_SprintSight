#!/bin/sh
# enroot --rc entrypoint: no bash/curl in the ollama image, keep this POSIX sh.
set -e

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama to become ready..."
until ollama list >/dev/null 2>&1; do
  sleep 2
done

# alias|base model|Modelfile, mirrors docker-compose.yaml model-init
for entry in \
  "sprintsight-llama|llama3.2|Modelfile.llama" \
  "sprintsight-qwen|qwen3:8b|Modelfile.qwen" \
  "sprintsight-mistral|mistral:7b|Modelfile.mistral" \
  "sprintsight-gemma|gemma4:12b|Modelfile.gemma" \
  "sprintsight-judge-phi|phi4:14b|Modelfile.phi"
do
  alias=$(echo "$entry" | cut -d'|' -f1)
  base=$(echo "$entry" | cut -d'|' -f2)
  modelfile=$(echo "$entry" | cut -d'|' -f3)
  if ! ollama list | grep -q "$alias"; then
    echo "Pulling $base and creating $alias..."
    ollama pull "$base"
    ollama create "$alias" -f "/mnt/models/$modelfile"
  fi
done

echo "All SprintSight models ready. Serving until job time limit..."
wait "$SERVE_PID"
