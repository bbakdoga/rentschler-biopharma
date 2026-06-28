#!/usr/bin/env bash
# Launch the BPR Validation Tool GUI with the cloud vision-LLM OCR backend
# (Qwen2.5-VL-72B via OpenRouter) for best handwriting accuracy.
#
# Run offline Tesseract instead?  →  source .venv/bin/activate && python main.py
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "No .venv found — run ./install.sh first." >&2
    exit 1
fi
source .venv/bin/activate

# Hybrid OCR: Tesseract geometry + Qwen2.5-VL-72B re-reads handwriting via an
# OpenAI-compatible cloud endpoint (OpenRouter).
export OCR_BACKEND=api
export OPENAI_API_BASE="https://openrouter.ai/api/v1"
export OPENAI_VL_MODEL="qwen/qwen2.5-vl-72b-instruct"

# The OpenRouter API key lives in an untracked .env (copy .env.example → .env).
# It is NOT committed — GitHub blocks pushing secrets, and keys shouldn't live in
# git history anyway.
if [ -f .env ]; then
    set -a; source ./.env; set +a
fi
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "OPENAI_API_KEY is not set." >&2
    echo "Copy .env.example to .env and put your OpenRouter key in it:" >&2
    echo "    cp .env.example .env  &&  edit .env" >&2
    exit 1
fi

python main.py
