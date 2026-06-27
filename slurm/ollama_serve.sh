#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Start an offline Ollama vision server inside an INTERACTIVE GPU allocation.
#
# Use this when you want to keep the GUI / tool running on a login node while
# the model runs on the GPU node you were allocated (e.g. via rz-launch/salloc).
#
#   1) Get an interactive GPU shell, e.g.:
#        salloc -N 1 --gres=gpu:1 -t 4:00:00      # (or your site's rz-launch)
#   2) Inside that shell, run:
#        ./slurm/ollama_serve.sh
#   3) It prints the address to point the tool at, e.g.:
#        export OLLAMA_HOST=http://node042:11434
#      Then, from where you run the tool (this node or a login node that can
#      reach it):
#        OCR_BACKEND=llm OLLAMA_HOST=http://node042:11434 python main.py batch.pdf
#
# Leave this running; Ctrl-C stops the server.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODEL="${OLLAMA_VL_MODEL:-qwen2.5vl:7b}"
PORT="${OLLAMA_PORT:-11434}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
mkdir -p "$OLLAMA_MODELS"

# Bind to all interfaces so other nodes (e.g. a login node) can reach it.
export OLLAMA_HOST="0.0.0.0:${PORT}"

module load ollama/latest 2>/dev/null || module load ollama
module load python/3.12 2>/dev/null || true

echo "Starting Ollama on $HOSTNAME:${PORT} (model: $MODEL)"
nvidia-smi -L || true

ollama serve &
OLLAMA_PID=$!
trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT

# Wait for readiness, then pull the model.
for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:${PORT}/api/tags" >/dev/null 2>&1 && break
    sleep 1
done
ollama pull "$MODEL"

cat <<EOF

================================================================================
 Ollama is ready.  Point the BPR tool at it with:

   export OCR_BACKEND=llm
   export OLLAMA_HOST=http://$HOSTNAME:${PORT}
   export OLLAMA_VL_MODEL=$MODEL
   python main.py /path/to/batch.pdf

 (If running on this same node you may use http://127.0.0.1:${PORT}.)
 Press Ctrl-C here to stop the server.
================================================================================
EOF

wait "$OLLAMA_PID"
