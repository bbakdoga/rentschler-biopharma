import fitz          # PyMuPDF
import io
from pathlib import Path
from PIL import Image
from config import DISPLAY_IMAGE_EXTENSION, IMAGE_DPI, TEMP_DIR


class PDFProcessor:
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.doc = fitz.open(str(pdf_path))
        self.out_dir = TEMP_DIR / self.pdf_path.stem
        self.out_dir.mkdir(exist_ok=True, parents=True)

    def page_count(self) -> int:
        return len(self.doc)

    def get_page_image(self, page_num: int) -> Image.Image:
        page = self.doc[page_num]
        scale = IMAGE_DPI / 72
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        return Image.open(io.BytesIO(pix.tobytes("png")))

    def save_page_image(self, page_num: int) -> Path:
        img = self.get_page_image(page_num)
        path = self.page_image_path(page_num)
        img.save(path, "PNG")
        return path

    def page_image_path(self, page_num: int) -> Path:
        """Return the path for the lightweight internal viewer image."""
        return self.out_dir / f"page_{page_num + 1:03d}{DISPLAY_IMAGE_EXTENSION}"

    def get_embedded_text(self, page_num: int) -> str:
        """Return any digitally-embedded text (empty for pure scans)."""
        return self.doc[page_num].get_text()

    def close(self):
        self.doc.close()
