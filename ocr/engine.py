"""
OCR backend factory.

Selects the OCR engine from config (``OCR_BACKEND``, env-overridable):

  * ``tesseract`` (default) — CPU-only Tesseract, no GPU required.
  * ``llm``                  — hybrid Tesseract + offline Ollama vision model
                               for handwriting (needs a running Ollama server,
                               typically on a GPU node).

Both engines expose the same interface, so callers don't branch on backend:

    engine.extract_words_with_conf(ocr_img, source_img=display_img) -> list[dict]
    engine.extract_text(ocr_img, source_img=display_img)            -> str
"""
from config import OCR_BACKEND
from ocr.tesseract_engine import TesseractEngine


def get_ocr_engine():
    if OCR_BACKEND.strip().lower() == "llm":
        from ocr.llm_engine import LLMEngine
        return LLMEngine()
    return TesseractEngine()
