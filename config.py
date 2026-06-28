import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "bpr_tool.db"
TEMP_DIR = BASE_DIR / "temp_pages"
TEMP_DIR.mkdir(exist_ok=True)

# Tesseract: override with env var TESSERACT_CMD if needed
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
OCR_LANG = "deu+eng"
# OCR and viewer previews intentionally use a moderate resolution for speed.
# Annotated exports use the original PDF and do not depend on this value.
IMAGE_DPI = 225
DISPLAY_IMAGE_FORMAT = "JPEG"
DISPLAY_IMAGE_EXTENSION = ".jpg"
DISPLAY_JPEG_QUALITY = 88

# OCR confidence (0–100) below which a read is treated as "uncertain" and
# flagged in the viewer / report. Handwriting and poor scans score low here.
OCR_CONFIDENCE_WARN = 60

# ── OCR backend ───────────────────────────────────────────────────────────────
# "tesseract" (default, CPU-only), "llm" (hybrid Tesseract geometry + an offline
# Ollama vision model), or "api" (same hybrid pipeline but the vision reads go to
# a hosted OpenAI-compatible endpoint serving a strong OPEN-WEIGHTS model). Switch
# with:  OCR_BACKEND=llm  or  OCR_BACKEND=api  (env or here).
OCR_BACKEND = os.environ.get("OCR_BACKEND", "tesseract")

# ── Hosted API backend (OCR_BACKEND=api) ───────────────────────────────────────
# An OpenAI-compatible /v1 vision endpoint. The default model — Qwen2.5-VL-72B —
# is OPEN WEIGHTS and the same family as the offline qwen2.5vl:7b above, so a demo
# run through the API matches an offline GPU deployment of the identical weights
# (the same model file run under Ollama/vLLM on a GPU node). This keeps the claim
# "the same model runs offline and yields the same results" literally true.
# Works with OpenRouter / DashScope / Together / Hyperbolic / a local vLLM / a
# remote Ollama's /v1 endpoint — set the base URL and key to match your provider.
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VL_MODEL = os.environ.get("OPENAI_VL_MODEL", "qwen/qwen2.5-vl-72b-instruct")
OPENAI_TIMEOUT = float(os.environ.get("OPENAI_TIMEOUT", "180"))

# Offline Ollama vision server. On the cluster this runs on a GPU node; point
# OLLAMA_HOST at it (e.g. http://node042:11434). Defaults to a local server.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Vision model tag pulled/served by Ollama. qwen2.5vl is strong at handwriting;
# alternatives: "llama3.2-vision:11b", "minicpm-v", "granite3.2-vision".
OLLAMA_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen2.5vl:7b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "180"))
# Max tokens for a whole-page transcription. A dense BPR page needs far more
# than the per-crop budget, or the structured read is truncated mid-page.
OLLAMA_PAGE_NUM_PREDICT = int(os.environ.get("OLLAMA_PAGE_NUM_PREDICT", "2048"))
# Context window for a whole-page read. A full-page image is ~3.5–4k tokens on
# its own; with the prompt and the generated transcription it must exceed
# Ollama's 4096 default or the request is rejected (exceed_context_size_error).
OLLAMA_PAGE_NUM_CTX = int(os.environ.get("OLLAMA_PAGE_NUM_CTX", "8192"))
# Use the vision-LLM's structured whole-page read as the authoritative text for
# section ID + regex extraction (keeps Tesseract word boxes for the viewer).
# Only applies when OCR_BACKEND=llm. Turn off to revert to the word-patch text.
LLM_STRUCTURED_PAGE = os.environ.get("LLM_STRUCTURED_PAGE", "1") not in ("0", "")

# Only spend a (slow) vision-LLM page read on pages that actually contain
# handwriting. We detect that from Tesseract's confidences: handwriting reads
# low. A page is treated as handwritten — and sent to the LLM — when it has at
# least LLM_PAGE_HW_MIN_WORDS words at/below LLM_CORRECT_BELOW confidence, OR
# that fraction of low-confidence words exceeds LLM_PAGE_HW_MIN_FRAC. Printed
# pages stay on fast Tesseract-only text. Set LLM_PAGE_HW_MIN_WORDS=0 to force
# the LLM on every page.
LLM_PAGE_HW_MIN_WORDS = int(os.environ.get("LLM_PAGE_HW_MIN_WORDS", "6"))
LLM_PAGE_HW_MIN_FRAC = float(os.environ.get("LLM_PAGE_HW_MIN_FRAC", "0.10"))

# Re-read a word run with the vision-LLM when Tesseract confidence is at or
# below this (handwriting tends to score low). Defaults to the warn threshold.
LLM_CORRECT_BELOW = int(os.environ.get("LLM_CORRECT_BELOW",
                                       str(OCR_CONFIDENCE_WARN)))
# Safety cap on vision-LLM crops per page (bounds runtime on noisy scans).
LLM_MAX_CROPS_PER_PAGE = int(os.environ.get("LLM_MAX_CROPS_PER_PAGE", "60"))
# Padding (px) added around a crop, and the minimum crop size the model sees
# (smaller crops are upscaled) — both in OCR-image pixels.
LLM_CROP_PAD = int(os.environ.get("LLM_CROP_PAD", "10"))
LLM_MIN_CROP_WIDTH = int(os.environ.get("LLM_MIN_CROP_WIDTH", "320"))
LLM_MIN_CROP_HEIGHT = int(os.environ.get("LLM_MIN_CROP_HEIGHT", "64"))

# Validation tolerances
CALC_TOLERANCE = 2.0        # absolute tolerance for numeric calculations
BELADUNG_MIN = 7.0          # g_Cake / L_Milk
BELADUNG_MAX = 19.0
WIPP_MIN = 20
WIPP_MAX = 30               # Hübe/min

# Hold temperature ranges
HOLD_TEMP_COLD = (2.0, 8.0)     # °C
HOLD_TEMP_WARM = (18.0, 25.0)   # °C
HOLD_TEMP_HOT  = (57.0, 72.0)   # °C (approximate)
