#!/usr/bin/env python3
"""
Smoke test for the offline vision OCR backend.

Confirms the configured Ollama server is reachable and that the vision model
can transcribe handwriting. Run after starting the server:

    OCR_BACKEND=llm OLLAMA_HOST=http://<node>:11434 python slurm/check_ollama.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

from config import OLLAMA_HOST, OLLAMA_VL_MODEL
from ocr.ollama_client import OllamaVisionClient


def main() -> int:
    client = OllamaVisionClient()
    print(f"Server : {OLLAMA_HOST}")
    print(f"Model  : {OLLAMA_VL_MODEL}")

    if not client.is_available():
        print("✗ Server not reachable. Is `ollama serve` running and is "
              "OLLAMA_HOST correct?")
        return 1
    print("✓ Server reachable.")

    # A trivial synthetic image with text to confirm the model responds.
    img = Image.new("RGB", (360, 90), "white")
    ImageDraw.Draw(img).text((12, 30), "12,5 kg", fill="black")
    out = client.transcribe(img)
    if out is None:
        print("✗ Model request failed (see stderr above).")
        return 1
    print(f"✓ Model responded: {out!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
