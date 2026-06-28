"""
OCR backend factory.

Selects the OCR engine from config (``OCR_BACKEND``, env-overridable):

    * ``paddleocr`` (default) — CPU-only PaddleOCR, no GPU required.
    * ``llm``                 — hybrid PaddleOCR + offline Ollama vision model
                                                            for handwriting (needs a running Ollama server,
                                                            typically on a GPU node).
All engines expose the same interface, so callers don't branch on backend:

        engine.extract_words_with_conf(ocr_img, source_img=display_img) -> list[dict]
        engine.extract_text(ocr_img, source_img=display_img)            -> str
"""
from config import OCR_BACKEND
from ocr.paddle_engine import PaddleOCREngine


def get_ocr_engine():
    backend = OCR_BACKEND.strip().lower()
    if backend == "llm":
        from ocr.llm_engine import LLMEngine
        return LLMEngine()
    return PaddleOCREngine()
