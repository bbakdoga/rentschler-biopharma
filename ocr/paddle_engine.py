"""
PaddleOCR backend.

This engine keeps the same public contract used by the rest of the
application:

    extract_words_with_conf(img, source_img=None) -> list[dict]
    extract_text(img, source_img=None)            -> str

The returned word dictionaries match the format expected by the field
extractors and the viewer overlays: text, confidence, and an axis-aligned
bounding box in OCR-image pixels.
"""
from __future__ import annotations

import re
from typing import Iterable

import numpy as np
from PIL import Image

from config import PADDLEOCR_LANG, PADDLEOCR_USE_ANGLE_CLS
from extract.generic_extractor import words_to_text


class PaddleOCREngine:
    def __init__(self, lang: str = PADDLEOCR_LANG,
                 use_angle_cls: bool = PADDLEOCR_USE_ANGLE_CLS):
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR is not installed. Install the project dependencies "
                "with `pip install -r requirements.txt`."
            ) from exc

        # Lazy model creation keeps imports lightweight until OCR is actually
        # needed, but the first call may still download PaddleOCR model files.
        self._ocr = PaddleOCR(lang=lang, use_angle_cls=use_angle_cls,
                              show_log=False)

    def extract_text(self, img: Image.Image, psm: int = 6,
                     source_img: Image.Image | None = None) -> str:
        return words_to_text(self.extract_words_with_conf(img, source_img=source_img))

    def extract_words_with_conf(self, img: Image.Image,
                                source_img: Image.Image | None = None
                                ) -> list[dict]:
        ocr_img = source_img if source_img is not None else img
        raw = self._ocr.ocr(self._to_bgr_array(ocr_img), cls=self.use_angle_cls)
        lines = self._normalize_result(raw)
        if not lines:
            return []

        words: list[dict] = []
        for box, text, score in self._iter_lines(lines):
            words.extend(self._split_line(box, text, score))
        return words

    @staticmethod
    def _to_bgr_array(img: Image.Image) -> np.ndarray:
        rgb = np.asarray(img.convert("RGB"))
        return rgb[:, :, ::-1].copy()

    @staticmethod
    def _normalize_result(raw) -> list:
        if not raw:
            return []
        # PaddleOCR returns either a single image result:
        #   [[box, (text, score)], ...]
        # or a one-item batch wrapper in some versions:
        #   [[[box, (text, score)], ...]]
        if (isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list)
                and raw[0] and isinstance(raw[0][0], list)
                and len(raw[0][0]) == 2):
            return raw[0]
        return raw if isinstance(raw, list) else []

    @staticmethod
    def _iter_lines(lines: Iterable) -> Iterable[tuple[tuple[int, int, int, int], str, int]]:
        for line in lines:
            if not line or len(line) < 2:
                continue
            box, rec = line[0], line[1]
            text = ""
            score = 0.0
            if isinstance(rec, (list, tuple)) and len(rec) >= 2:
                text = str(rec[0] or "")
                score = float(rec[1] or 0.0)
            elif isinstance(rec, str):
                text = rec
            if not text.strip():
                continue
            yield PaddleOCREngine._box_to_bbox(box), text, max(0, min(100, int(round(score * 100))))

    @staticmethod
    def _box_to_bbox(box) -> tuple[int, int, int, int]:
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        x0, y0 = int(min(xs)), int(min(ys))
        x1, y1 = int(max(xs)), int(max(ys))
        return x0, y0, max(x1 - x0, 1), max(y1 - y0, 1)

    @staticmethod
    def _split_line(box: tuple[int, int, int, int], text: str, conf: int) -> list[dict]:
        tokens = [tok for tok in re.split(r"\s+", text.strip()) if tok]
        if not tokens:
            return []

        x0, y0, width, height = box
        if len(tokens) == 1:
            return [{
                "text": tokens[0],
                "conf": conf,
                "x": x0,
                "y": y0,
                "w": width,
                "h": height,
            }]

        weights = [max(len(tok), 1) for tok in tokens]
        total = sum(weights)
        cursor = x0
        out: list[dict] = []
        for idx, (token, weight) in enumerate(zip(tokens, weights)):
            if idx == len(tokens) - 1:
                token_w = x0 + width - cursor
            else:
                token_w = max(int(round(width * weight / total)), 1)
                remaining = x0 + width - cursor
                if token_w > remaining:
                    token_w = max(remaining, 1)
            out.append({
                "text": token,
                "conf": conf,
                "x": cursor,
                "y": y0,
                "w": token_w,
                "h": height,
            })
            cursor += token_w
        return out