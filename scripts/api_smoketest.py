#!/usr/bin/env python3
"""
One-call smoke test for the hosted vision API backend (OCR_BACKEND=api).

Confirms your API key / base URL / model work and shows the model's structured
read of a single page — by default the Bilanzierung page, so you can eyeball the
handwriting accuracy before spending a full-document run.

    export OPENAI_API_KEY="...your key..."
    python scripts/api_smoketest.py                       # page 11 of the default PDF
    python scripts/api_smoketest.py <pdf> <page_number>   # any page

Provider knobs (env): OPENAI_API_BASE, OPENAI_VL_MODEL  (see config.py).
"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_VL_MODEL
from ingest.pdf_processor import PDFProcessor
from ingest.image_preprocess import ImagePreprocessor
from ocr.api_client import OpenAIVisionClient

_DEFAULT_PDF = "/Users/haniehmesri/Downloads/Scanned_batch_documentation.pdf"


def main() -> int:
    if not OPENAI_API_KEY:
        print("OPENAI_API_KEY is not set. Run:\n"
              '  export OPENAI_API_KEY="...your key..."', file=sys.stderr)
        return 2

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PDF
    page = int(sys.argv[2]) if len(sys.argv) > 2 else 11
    if not Path(pdf_path).exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    print(f"endpoint : {OPENAI_API_BASE}")
    print(f"model    : {OPENAI_VL_MODEL}")
    print(f"page     : {page} of {pdf_path}\n")

    pdf = PDFProcessor(pdf_path)
    pre = ImagePreprocessor()
    proc, disp = pre.process_full_page_with_display(pdf.get_page_image(page - 1))
    client = OpenAIVisionClient()

    t0 = time.time()
    text = client.read_structured_page(disp)
    dt = time.time() - t0
    pdf.close()

    if not text:
        print(f"FAILED after {dt:.1f}s — no text returned. Check the key, "
              f"base URL and model id (see the [api] error above).",
              file=sys.stderr)
        return 1
    print(f"OK — {len(text)} chars in {dt:.1f}s\n" + "-" * 60)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
