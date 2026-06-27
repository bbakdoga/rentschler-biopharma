"""
Thin HTTP client for an offline Ollama vision model.

Ollama exposes a local REST API (default http://127.0.0.1:11434). We talk to
its ``/api/generate`` endpoint with one or more base64-encoded images, which is
all a vision model needs to transcribe a crop or a whole page.

Only the Python standard library is used so this adds no dependency and runs on
the bare cluster module Python. Every network failure degrades gracefully:
methods return ``None`` and the caller keeps the Tesseract result.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request

from config import (
    OLLAMA_HOST, OLLAMA_VL_MODEL, OLLAMA_TIMEOUT, OLLAMA_PAGE_NUM_PREDICT,
    OLLAMA_PAGE_NUM_CTX,
)


# A short, focused instruction for a single filled-in field (the handwriting).
HANDWRITING_PROMPT = (
    "This is a small crop from a scanned pharmaceutical batch production "
    "record. Transcribe the text exactly as it appears, including any "
    "handwritten entries, numbers, dates, times, check marks or initials. "
    "Preserve digits and decimal separators (',' or '.') exactly. "
    "Output ONLY the transcribed text - no explanation, no quotes, no labels. "
    "If the crop is empty, output nothing."
)

# Instruction for reading a whole page (used as a robust fallback).
PAGE_PROMPT = (
    "This is a scanned page from a pharmaceutical batch production record that "
    "may contain handwritten entries. Transcribe ALL text on the page. "
    "Keep the original line order and use spaces to separate the label column "
    "from the filled-in value column. Include handwritten values, numbers, "
    "dates, times and initials exactly. Output only the transcription."
)

# Instruction for a STRUCTURED whole-page read. This is the authoritative text
# that drives section identification and the regex field extractors, so the
# rules below matter: the printed German labels must be preserved verbatim (the
# extractors are anchored to them) and each label must stay on the same line as
# the value filled in next to it, so a label is never paired with the wrong
# column's number.
STRUCTURED_PAGE_PROMPT = (
    "This is a scanned page from a pharmaceutical batch production record "
    "(German) that mixes printed template text with handwritten entries. "
    "Transcribe the whole page as plain text, following these rules exactly:\n"
    "1. Preserve the printed German labels and section headings VERBATIM "
    "(e.g. 'Bilanzierung', 'm Brutto', 'm Tara', 'm Netto', 'Batch No.', "
    "'Beladung'). Do not translate, abbreviate or reword them.\n"
    "2. Put each label on the SAME line as the value filled in next to it, in "
    "reading order, label first then value. Never move a value to a different "
    "label's line. If a field is blank, leave the value empty.\n"
    "3. Put every section heading on its own line, including its number if "
    "printed (e.g. '5.3.1 Bilanzierung').\n"
    "4. Transcribe a table one row per line, left to right; separate the cells "
    "of a row with two spaces.\n"
    "5. Reproduce all handwritten values, numbers, dates, times, decimal "
    "separators (',' or '.'), check marks and initials EXACTLY as written.\n"
    "Output only the transcription, no commentary."
)


class OllamaVisionClient:
    """Minimal client for an Ollama vision model."""

    def __init__(self, host: str = OLLAMA_HOST,
                 model: str = OLLAMA_VL_MODEL,
                 timeout: float = OLLAMA_TIMEOUT):
        self.endpoint = host.rstrip("/") + "/api/generate"
        self.model = model
        self.timeout = timeout
        self._warned = False

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _b64_png(img) -> str:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _generate(self, prompt: str, img, num_predict: int = 512,
                  num_ctx: int | None = None) -> str | None:
        options = {"temperature": 0.0, "num_predict": num_predict}
        # A full-page image alone is ~3.5–4k tokens; the context must hold the
        # image + prompt + transcription or Ollama rejects the request.
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [self._b64_png(img)],
            "stream": False,
            # Greedy decoding → deterministic, faithful transcription.
            "options": options,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return (body.get("response") or "").strip()
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            if not self._warned:
                print(f"[ollama] vision request failed ({exc}); "
                      f"falling back to Tesseract text.", file=sys.stderr)
                self._warned = True
            return None

    # ── public API ────────────────────────────────────────────────────────────
    def transcribe(self, img, prompt: str = HANDWRITING_PROMPT) -> str | None:
        """Transcribe a single crop (typically one handwritten field)."""
        return self._generate(prompt, img)

    def read_page(self, img, prompt: str = PAGE_PROMPT) -> str | None:
        """Transcribe a whole page (fallback when there are no word boxes)."""
        return self._generate(prompt, img, num_predict=OLLAMA_PAGE_NUM_PREDICT,
                              num_ctx=OLLAMA_PAGE_NUM_CTX)

    def read_structured_page(self, img,
                             prompt: str = STRUCTURED_PAGE_PROMPT) -> str | None:
        """Transcribe a whole page as structured label/value text — the
        authoritative source for section ID and the regex field extractors."""
        return self._generate(prompt, img, num_predict=OLLAMA_PAGE_NUM_PREDICT,
                              num_ctx=OLLAMA_PAGE_NUM_CTX)

    def is_available(self) -> bool:
        """Best-effort health check against the Ollama server."""
        base = self.endpoint.rsplit("/api/", 1)[0]
        try:
            with urllib.request.urlopen(base + "/api/tags",
                                        timeout=min(self.timeout, 10)) as resp:
                return resp.status == 200
        except Exception:
            return False
