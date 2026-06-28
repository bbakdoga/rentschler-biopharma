#!/usr/bin/env bash
# One-shot setup for BPR Validation Tool on macOS / Linux
set -e

echo "=== BPR Validation Tool — setup ==="

# 1. Python venv — requires Python >= 3.10 (the code uses `X | None` syntax).
#    Override the interpreter with PYTHON=... (e.g. on the cluster:
#      module load python/3.12 && PYTHON=python3 ./install.sh)
PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    have="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo '?')"
    echo "ERROR: need Python >= 3.10, but '$PYTHON' is $have." >&2
    echo "On the cluster:  module load python/3.12 && PYTHON=python3 ./install.sh" >&2
    exit 1
fi
echo "Using $("$PYTHON" --version)"

rm -rf .venv
"$PYTHON" -m venv .venv
source .venv/bin/activate

# 2. Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 3. PaddleOCR runtime
# PaddleOCR is installed via requirements.txt. The first OCR run may download
# model files automatically into the local cache.

echo ""
echo "Setup complete."
echo "Activate with:  source .venv/bin/activate"
echo "Run with:       python main.py"
