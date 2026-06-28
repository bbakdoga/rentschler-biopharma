"""
OCR backend factory.

Selects the OCR engine from config (``OCR_BACKEND``, env-overridable):

  * ``tesseract`` (default) — CPU-only Tesseract, no GPU required.
  * ``llm``                  — hybrid Tesseract + offline Ollama vision model
                               for handwriting (needs a running Ollama server,
                               typically on a GPU node).
  * ``api``                  — same hybrid pipeline, but vision reads go to a
                               hosted OpenAI-compatible endpoint serving a strong
                               open-weights model (default Qwen2.5-VL-72B). The
                               model is open weights, so the API demo matches an
                               offline GPU deployment of the identical model.

All engines expose the same interface, so callers don't branch on backend:

    engine.extract_words_with_conf(ocr_img, source_img=display_img) -> list[dict]
    engine.extract_text(ocr_img, source_img=display_img)            -> str
"""
from config import OCR_BACKEND
from ocr.tesseract_engine import TesseractEngine


def get_ocr_engine():
    backend = OCR_BACKEND.strip().lower()
    if backend == "api":
        from ocr.llm_engine import LLMEngine
        from ocr.api_client import OpenAIVisionClient
        return LLMEngine(client=OpenAIVisionClient())
    if backend == "llm":
        from ocr.llm_engine import LLMEngine
        return LLMEngine()
    return TesseractEngine()
