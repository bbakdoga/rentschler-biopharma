#!/usr/bin/env bash
# One-shot setup for BPR Validation Tool on macOS / Linux
set -e

echo "=== BPR Validation Tool — setup ==="

# 1. Python venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Python packages
pip install --upgrade pip
pip install -r requirements.txt

# 3. Tesseract
if ! command -v tesseract &>/dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "Installing Tesseract via Homebrew…"
        brew install tesseract tesseract-lang
    else
        echo "Installing Tesseract via apt…"
        sudo apt-get install -y tesseract-ocr tesseract-ocr-deu
    fi
fi

echo ""
echo "Setup complete."
echo "Activate with:  source .venv/bin/activate"
echo "Run with:       python main.py"
