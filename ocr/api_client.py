"""
OpenAI-compatible vision client for a hosted strong open-weights model.

Used when ``OCR_BACKEND=api``. Talks to any OpenAI-compatible
``/v1/chat/completions`` endpoint (OpenRouter, Alibaba DashScope, Together,
Hyperbolic, a local vLLM server, or a remote Ollama's ``/v1`` endpoint) that
serves a vision model.

The default model — Qwen2.5-VL-72B — is OPEN WEIGHTS and the same family as the
offline ``qwen2.5vl:7b``. Running it through a hosted API for a demo therefore
produces the same results as an offline GPU deployment of the identical weights,
so "the same model runs offline" is a faithful claim, not a stand-in.

This exposes the SAME interface as :class:`OllamaVisionClient`
(``transcribe`` / ``read_page`` / ``read_structured_page`` / ``is_available``)
so :class:`LLMEngine` is backend-agnostic. Only the Python standard library is
used; every network failure degrades gracefully to ``None`` and the caller keeps
the Tesseract result.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import time
import urllib.error
import urllib.request

from config import (
    OPENAI_API_BASE, OPENAI_API_KEY, OPENAI_VL_MODEL, OPENAI_TIMEOUT,
    OLLAMA_PAGE_NUM_PREDICT,
)
from ocr.ollama_client import (
    HANDWRITING_PROMPT, PAGE_PROMPT, STRUCTURED_PAGE_PROMPT,
)

# Transient failures worth retrying: rate limits (429) and upstream 5xx. A hosted
# router (OpenRouter) returns 429 when one provider is momentarily overloaded; a
# retry often lands on a healthy provider.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BASE_BACKOFF = 1.5      # seconds, exponential
_MAX_BACKOFF = 20.0


class OpenAIVisionClient:
    """Minimal client for an OpenAI-compatible vision model."""

    def __init__(self, base: str = OPENAI_API_BASE,
                 api_key: str = OPENAI_API_KEY,
                 model: str = OPENAI_VL_MODEL,
                 timeout: float = OPENAI_TIMEOUT):
        self.base = base.rstrip("/")
        self.endpoint = self.base + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._warned = False

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _data_uri(img) -> str:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return "data:image/png;base64," + b64

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _warn(self, msg: str):
        if not self._warned:
            print(f"[api] vision request failed: {msg}\n      falling back to "
                  f"Tesseract text.", file=sys.stderr)
            self._warned = True

    @staticmethod
    def _backoff(exc, attempt: int) -> float:
        """Seconds to wait before the next retry — honour ``Retry-After`` when
        the server sends it, otherwise exponential backoff."""
        retry_after = getattr(exc, "headers", None)
        if retry_after is not None:
            val = retry_after.get("Retry-After")
            if val:
                try:
                    return min(float(val), _MAX_BACKOFF)
                except ValueError:
                    pass
        return min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF)

    def _generate(self, prompt: str, img, max_tokens: int = 512) -> str | None:
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": self._data_uri(img)}},
                ],
            }],
            # Greedy decoding → deterministic, faithful transcription.
            "temperature": 0.0,
            "max_tokens": max_tokens,
        }
        # On OpenRouter, prefer higher-throughput providers and allow fallback
        # so one rate-limited backend doesn't fail the whole request.
        if "openrouter" in self.base:
            payload["provider"] = {"sort": "throughput", "allow_fallbacks": True}
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(self.endpoint, data=data,
                                         headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return (body["choices"][0]["message"]["content"] or "").strip()
            except urllib.error.HTTPError as exc:
                # Surface the provider's error body (e.g. "Invalid API-key",
                # "Model not exist") — the status code alone isn't enough.
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace").strip()[:400]
                except Exception:
                    pass
                if exc.code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff(exc, attempt))
                    continue            # transient (rate limit / 5xx) → retry
                self._warn(f"HTTP {exc.code} {exc.reason}: {detail}")
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(_BASE_BACKOFF * (2 ** attempt), _MAX_BACKOFF))
                    continue            # network blip → retry
                self._warn(str(exc))
                return None
            except (ValueError, KeyError, IndexError) as exc:
                self._warn(f"bad response ({exc})")   # not retryable
                return None
        return None

    # ── public API (mirrors OllamaVisionClient) ─────────────────────────────────
    def transcribe(self, img, prompt: str = HANDWRITING_PROMPT) -> str | None:
        """Transcribe a single crop (one handwritten field)."""
        return self._generate(prompt, img)

    def read_page(self, img, prompt: str = PAGE_PROMPT) -> str | None:
        """Transcribe a whole page (fallback when there are no word boxes)."""
        return self._generate(prompt, img, max_tokens=OLLAMA_PAGE_NUM_PREDICT)

    def read_structured_page(self, img,
                             prompt: str = STRUCTURED_PAGE_PROMPT) -> str | None:
        """Structured whole-page read — authoritative text for section ID and
        the regex field extractors."""
        return self._generate(prompt, img, max_tokens=OLLAMA_PAGE_NUM_PREDICT)

    def is_available(self) -> bool:
        """Best-effort health check: GET /models, else assume reachable when a
        key is configured (most hosted endpoints reject anonymous pings)."""
        try:
            req = urllib.request.Request(self.base + "/models",
                                         headers=self._headers())
            with urllib.request.urlopen(
                    req, timeout=min(self.timeout, 10)) as resp:
                return resp.status == 200
        except Exception:
            return bool(self.api_key)
