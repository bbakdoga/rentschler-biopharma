"""
Hybrid OCR engine: Tesseract geometry + offline vision-LLM handwriting.

Tesseract reads printed labels well but struggles with handwriting. This engine
keeps Tesseract for the page layout (word boxes, confidences) and re-reads only
the *low-confidence runs* — i.e. the handwritten, filled-in values — with an
offline Ollama vision model, replacing their text while keeping their bounding
boxes.

Because it implements the same ``extract_words_with_conf`` / ``extract_text``
contract as :class:`TesseractEngine`, it is a drop-in replacement: everything
downstream (line reconstruction, label/value pairing, viewer overlays, the
regex field extractors) keeps working unchanged and simply sees more accurate
text for the handwritten entries.
"""
from __future__ import annotations

from PIL import Image

from config import (
    LLM_CORRECT_BELOW,
    LLM_MAX_CROPS_PER_PAGE,
    LLM_CROP_PAD,
    LLM_MIN_CROP_WIDTH,
    LLM_MIN_CROP_HEIGHT,
    LLM_STRUCTURED_PAGE,
)
from ocr.tesseract_engine import TesseractEngine
from ocr.ollama_client import OllamaVisionClient
from extract.generic_extractor import _group_lines


class LLMEngine:
    """Tesseract for geometry, a vision-LLM for handwriting."""

    def __init__(self, threshold: int = LLM_CORRECT_BELOW,
                 max_crops: int = LLM_MAX_CROPS_PER_PAGE,
                 client=None):
        self.tess = TesseractEngine()
        # Inject any client exposing the OllamaVisionClient interface
        # (transcribe / read_page / read_structured_page); defaults to the
        # offline Ollama client. The api backend passes an OpenAIVisionClient.
        self.client = client if client is not None else OllamaVisionClient()
        self.threshold = threshold
        self.max_crops = max_crops

    # ── public API (mirrors TesseractEngine) ───────────────────────────────────
    def extract_text(self, img: Image.Image, psm: int = 6,
                     source_img: Image.Image | None = None) -> str:
        """Full-page read. Prefer the vision-LLM (handles handwriting); fall
        back to Tesseract if the server is unreachable."""
        page = self.client.read_page(source_img if source_img is not None else img)
        if page:
            return page
        return self.tess.extract_text(img, psm=psm)

    def structured_page_text(self, img: Image.Image,
                             source_img: Image.Image | None = None
                             ) -> str | None:
        """Authoritative structured whole-page transcription used for section
        identification and regex extraction. Returns ``None`` if the server is
        unreachable so the caller can fall back to the word-reconstructed text.
        Word boxes (geometry) still come from Tesseract via
        ``extract_words_with_conf`` — this only supplies better *text*."""
        return self.client.read_structured_page(
            source_img if source_img is not None else img)

    def extract_words_with_conf(self, img: Image.Image,
                                source_img: Image.Image | None = None
                                ) -> list[dict]:
        """Tesseract word boxes with handwritten (low-confidence) runs re-read
        by the vision-LLM. ``source_img`` is the colour display image that
        shares geometry with ``img``; crops come from it for better fidelity."""
        words = self.tess.extract_words_with_conf(img)
        if not words:
            # Nothing detected (e.g. a fully handwritten page). Let the caller
            # fall back to a full-page LLM read via extract_text().
            return words
        if LLM_STRUCTURED_PAGE:
            # Handwriting is recovered by the full-page structured read, not by
            # per-word crop re-reads. Skip the (slow) per-crop LLM calls and
            # return Tesseract's geometry + confidences unchanged — the caller
            # uses those confidences to decide whether the page even needs the
            # LLM, and the structured read supplies the accurate text.
            return words
        src = source_img if source_img is not None else img
        return self._correct(words, src)

    # ── handwriting correction ──────────────────────────────────────────────────
    def _correct(self, words: list[dict], src: Image.Image) -> list[dict]:
        """Replace each run of consecutive low-confidence words with a single
        word carrying the LLM transcription and the run's union bounding box."""
        out: list[dict] = []
        budget = self.max_crops
        for line in _group_lines(words):
            i, n = 0, len(line)
            while i < n:
                if budget > 0 and self._is_low(line[i]):
                    j = i
                    while j < n and self._is_low(line[j]):
                        j += 1
                    run = line[i:j]
                    merged = self._read_run(src, run)
                    if merged is not None:
                        budget -= 1
                        out.append(merged)
                    else:
                        out.extend(run)        # keep Tesseract guess on failure
                    i = j
                else:
                    out.append(line[i])
                    i += 1
        return out

    def _is_low(self, w: dict) -> bool:
        c = w.get("conf")
        return c is not None and 0 <= c <= self.threshold

    def _read_run(self, src: Image.Image, run: list[dict]) -> dict | None:
        x0 = min(w["x"] for w in run)
        y0 = min(w["y"] for w in run)
        x1 = max(w["x"] + w["w"] for w in run)
        y1 = max(w["y"] + w["h"] for w in run)

        pad = LLM_CROP_PAD
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1 = min(src.width, x1 + pad)
        cy1 = min(src.height, y1 + pad)
        crop = src.crop((cx0, cy0, cx1, cy1))

        # Upscale tiny crops so the model has enough pixels to work with.
        if crop.width < LLM_MIN_CROP_WIDTH or crop.height < LLM_MIN_CROP_HEIGHT:
            scale = max(LLM_MIN_CROP_WIDTH / max(crop.width, 1),
                        LLM_MIN_CROP_HEIGHT / max(crop.height, 1))
            scale = min(scale, 4.0)
            crop = crop.resize(
                (max(1, int(crop.width * scale)),
                 max(1, int(crop.height * scale))),
                Image.LANCZOS,
            )

        text = self.client.transcribe(crop)
        if text is None:                       # server error → keep Tesseract
            return None
        text = text.strip()
        if not text:                           # model saw nothing → keep guess
            return None
        return {
            "text": text,
            "conf": 95,                        # LLM-read, treat as confident
            "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
        }
