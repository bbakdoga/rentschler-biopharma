#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Self-contained GPU batch job: start an offline Ollama vision server on the
# allocated node, then run the BPR tool against it with the LLM OCR backend.
#
# Submit:   sbatch slurm/bpr_ocr_llm.sbatch /path/to/batch.pdf
# Output:   bpr-ocr-<jobid>.out / .err  (in the submit directory)
#
# Adjust --account / --gres / --constraint for your project and GPU type
# (see the cluster docs: e.g. --gres=gpu:v100:1, --account=WILLI).
# ─────────────────────────────────────────────────────────────────────────────
#SBATCH -J bpr-ocr
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH -p downtime-gpu
#SBATCH --gres=gpu:1
#SBATCH -t 04:00:00
#SBATCH -o bpr-ocr-%j.out
#SBATCH -e bpr-ocr-%j.err
#SBATCH --mail-type=END
## During the maintenance downtime the GPU partition is "downtime-gpu" (above).
## Outside downtime use:  #SBATCH -p gpu
## GPU types on downtime-gpu: a30 (most idle), v100, a100 — pin one if needed,
## e.g.  #SBATCH --gres=gpu:a30:1
## #SBATCH --account=YOUR_PROJECT

set -euo pipefail

PDF="${1:?Usage: sbatch slurm/bpr_ocr_llm.sbatch /path/to/batch.pdf}"

# Project root = parent of this script's directory.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$PROJECT_DIR"

# ── tunables (override via env at submit time, e.g. OLLAMA_VL_MODEL=...) ───────
MODEL="${OLLAMA_VL_MODEL:-qwen2.5vl:7b}"
PORT="${OLLAMA_PORT:-11434}"
# Persist downloaded model weights between jobs (a few GB per model).
export OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
mkdir -p "$OLLAMA_MODELS"

echo "Executing on $HOSTNAME  |  model=$MODEL  |  pdf=$PDF"
nvidia-smi -L || true

# ── load software ─────────────────────────────────────────────────────────────
module load ollama/latest        2>/dev/null || module load ollama
# The venv interpreter is a 3.10+ module Python; load it so it resolves here.
module load python/3.12          2>/dev/null || true
# Activate the project's Python venv (created by install.sh).
if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
else
    echo "WARNING: .venv not found — run ./install.sh first." >&2
fi

# ── start the Ollama server bound to localhost on this node ────────────────────
export OLLAMA_HOST="127.0.0.1:${PORT}"
ollama serve > "ollama-${SLURM_JOB_ID:-local}.log" 2>&1 &
OLLAMA_PID=$!
cleanup() { kill "$OLLAMA_PID" 2>/dev/null || true; }
trap cleanup EXIT

# Wait until the API answers (up to ~60s).
echo -n "Waiting for Ollama to come up"
for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${PORT}/api/tags" >/dev/null 2>&1; then
        echo " — ready."; break
    fi
    echo -n "."; sleep 1
done

# ── pull the vision model (no-op if already cached) ───────────────────────────
echo "Pulling model $MODEL …"
ollama pull "$MODEL"

# ── run the BPR tool with the LLM OCR backend ─────────────────────────────────
export OCR_BACKEND=llm
export OLLAMA_HOST="http://127.0.0.1:${PORT}"
export OLLAMA_VL_MODEL="$MODEL"

echo "Running BPR tool …"
python main.py "$PDF"
echo "Done."
