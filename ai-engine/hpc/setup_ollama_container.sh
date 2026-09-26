#!/bin/bash
# One-time setup: import the ollama/ollama Docker image as an enroot .sqsh
# file and create the named enroot container from it. Run once per account
# (re-run only if you want to refresh the image).
#
# Usage (from the origami login node):
#   bash hpc/setup_ollama_container.sh
#
# Find your actual partition/qos with: myinfo

set -e

PARTITION="${PARTITION:-project}"   # change to your assigned partition (see `myinfo`)
QOS="${QOS:-cs480qos}"               # change to your assigned qos (see `myinfo`)

IMAGE_SQSH="ollama+ollama+latest.sqsh"

if [ ! -f "$IMAGE_SQSH" ]; then
  echo "Importing ollama/ollama:latest into enroot..."
  srun --partition="$PARTITION" --qos="$QOS" --mem=4G --cpus-per-task=4 \
    enroot import docker://ollama/ollama:latest
fi

if ! enroot list | grep -qx ollama; then
  echo "Creating enroot container 'ollama' from $IMAGE_SQSH..."
  srun --partition="$PARTITION" --qos="$QOS" --mem=4G --cpus-per-task=4 \
    enroot create --name ollama "$IMAGE_SQSH"
fi

echo "Done. You can remove $IMAGE_SQSH now to save home-directory quota:"
echo "  rm $IMAGE_SQSH"
