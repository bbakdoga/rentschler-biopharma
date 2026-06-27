"""High-quality PDF export with OCR field bounding boxes.

The export is based on the original PDF. Bounding boxes are translated from
OCR pixels to native PDF coordinates and drawn as vectors, so text and scans
retain their original quality regardless of the lower preview/OCR DPI.
"""
from pathlib import Path

import fitz

from db.models import Batch, Field, Page
from db.session import get_session
from config import OCR_CONFIDENCE_WARN


# Keep this palette aligned with the page viewer.
BOX_COLORS = (
    "#E6194B", "#3CB44B", "#4363D8", "#F58231", "#911EB4", "#42D4F4",
    "#F032E6", "#BFAF00", "#469990", "#9A6324", "#800000", "#000075",
)


def _pdf_color(hex_color: str) -> tuple[float, float, float]:
    """Convert a CSS hex color to PyMuPDF's 0–1 RGB tuple."""
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))


class AnnotatedPDFExporter:
    """Overlay extracted-field boxes on a copy of a batch's source PDF."""

    def export(self, batch_id: int, out_path: str) -> None:
        session = get_session()
        document = None
        try:
            batch = session.get(Batch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            source = Path(batch.file_path or "")
            if not source.is_file():
                raise FileNotFoundError(
                    "The original PDF is no longer available. "
                    f"Expected it at: {source}"
                )

            destination = Path(out_path)
            if source.resolve() == destination.resolve():
                raise ValueError("Choose a different filename from the original PDF")

            document = fitz.open(source)
            if document.needs_pass:
                raise ValueError("Password-protected PDFs cannot be exported")

            pages = (
                session.query(Page)
                .filter(Page.batch_id == batch_id)
                .order_by(Page.page_num)
                .all()
            )
            for page_record in pages:
                page_index = page_record.page_num - 1
                if not 0 <= page_index < document.page_count:
                    continue
                if not page_record.ocr_width or not page_record.ocr_height:
                    continue

                pdf_page = document[page_index]
                fields = (
                    session.query(Field)
                    .filter(
                        Field.page_id == page_record.id,
                        Field.bbox_x.isnot(None),
                        Field.bbox_y.isnot(None),
                        Field.bbox_w.isnot(None),
                        Field.bbox_h.isnot(None),
                    )
                    .order_by(Field.id)
                    .all()
                )
                scale_x = pdf_page.rect.width / page_record.ocr_width
                scale_y = pdf_page.rect.height / page_record.ocr_height

                for index, field in enumerate(fields):
                    rect = fitz.Rect(
                        field.bbox_x * scale_x,
                        field.bbox_y * scale_y,
                        (field.bbox_x + field.bbox_w) * scale_x,
                        (field.bbox_y + field.bbox_h) * scale_y,
                    )
                    uncertain = (
                        field.confidence is not None
                        and field.confidence < OCR_CONFIDENCE_WARN
                    )
                    pdf_page.draw_rect(
                        rect,
                        color=_pdf_color(BOX_COLORS[index % len(BOX_COLORS)]),
                        width=1.5 if uncertain else 1.0,
                        dashes="[4 3]" if uncertain else None,
                        overlay=True,
                    )

            document.save(destination, garbage=4, deflate=True)
        finally:
            if document is not None:
                document.close()
            session.close()
