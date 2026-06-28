import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "bpr_tool.db"
TEMP_DIR = BASE_DIR / "temp_pages"
TEMP_DIR.mkdir(exist_ok=True)

# PaddleOCR language pack. "german" works well for the German forms used here.
PADDLEOCR_LANG = os.environ.get("PADDLEOCR_LANG", "german")
# PaddleOCR angle classifier improves rotated / skewed text lines.
PADDLEOCR_USE_ANGLE_CLS = os.environ.get("PADDLEOCR_USE_ANGLE_CLS", "true").lower() in {
    "1", "true", "yes", "on"
}
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
# "paddleocr" (default, CPU-only) or "llm" (PaddleOCR geometry + an offline
# Ollama vision model that re-reads the handwritten / low-confidence entries).
OCR_BACKEND = os.environ.get("OCR_BACKEND", "paddleocr")

# Offline Ollama vision server. On the cluster this runs on a GPU node; point
# OLLAMA_HOST at it (e.g. http://node042:11434). Defaults to a local server.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Vision model tag pulled/served by Ollama. qwen2.5vl is strong at handwriting;
# alternatives: "llama3.2-vision:11b", "minicpm-v", "granite3.2-vision".
OLLAMA_VL_MODEL = os.environ.get("OLLAMA_VL_MODEL", "qwen2.5vl:7b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "180"))

# Re-read a word run with the vision-LLM when OCR confidence is at or below
# this (handwriting tends to score low). Defaults to the warn threshold.
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
