import pytesseract
from PIL import Image
from config import TESSERACT_CMD, OCR_LANG

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


class TesseractEngine:
    def __init__(self, lang: str = OCR_LANG):
        self.lang = lang

    def extract_text(self, img: Image.Image, psm: int = 6) -> str:
        config = f"--psm {psm} --oem 3"
        try:
            return pytesseract.image_to_string(img, lang=self.lang, config=config)
        except Exception:
            # Fallback to English only
            return pytesseract.image_to_string(img, lang="eng", config=config)

    def extract_words_with_conf(self, img: Image.Image) -> list[dict]:
        config = "--psm 6 --oem 3"
        data = pytesseract.image_to_data(
            img, lang=self.lang, config=config,
            output_type=pytesseract.Output.DICT
        )
        results = []
        for i, text in enumerate(data["text"]):
            if text.strip():
                results.append({
                    "text": text,
                    "conf": int(data["conf"][i]),
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                })
        return results
