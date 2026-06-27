import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "bpr_tool.db"
TEMP_DIR = BASE_DIR / "temp_pages"
TEMP_DIR.mkdir(exist_ok=True)

# Tesseract: override with env var TESSERACT_CMD if needed
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
OCR_LANG = "deu+eng"
IMAGE_DPI = 300

# OCR confidence (0–100) below which a read is treated as "uncertain" and
# flagged in the viewer / report. Handwriting and poor scans score low here.
OCR_CONFIDENCE_WARN = 60

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
