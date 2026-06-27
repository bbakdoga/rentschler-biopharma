import cv2
import numpy as np
from PIL import Image


class ImagePreprocessor:

    @staticmethod
    def _to_cv2(img: Image.Image) -> np.ndarray:
        return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _to_pil(arr: np.ndarray) -> Image.Image:
        if len(arr.shape) == 2:                 # grayscale
            return Image.fromarray(arr)
        return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))

    @staticmethod
    def deskew(arr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        coords = np.column_stack(np.where(gray > 0))
        if len(coords) < 10:
            return arr
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) < 0.5:
            return arr
        h, w = arr.shape[:2]
        M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
        return cv2.warpAffine(arr, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)

    @staticmethod
    def enhance_page(arr: np.ndarray) -> np.ndarray:
        """Binarise for printed + form text; keeps enough contrast for handwriting."""
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        # Mild denoise
        gray = cv2.fastNlMeansDenoising(gray, h=8)
        # CLAHE boosts local contrast (helps faint handwriting)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        # Otsu binarisation
        _, binary = cv2.threshold(gray, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def enhance_handwriting(arr: np.ndarray) -> np.ndarray:
        """Adaptive threshold + slight dilation for handwritten fields."""
        gray = (arr if len(arr.shape) == 2
                else cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY))
        # 2× upscale before thresholding
        h, w = gray.shape[:2]
        gray = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        kernel = np.ones((2, 2), np.uint8)
        return cv2.dilate(binary, kernel, iterations=1)

    def process_full_page(self, img: Image.Image) -> Image.Image:
        arr = self._to_cv2(img)
        arr = self.deskew(arr)
        return self._to_pil(self.enhance_page(arr))

    def process_full_page_with_display(self, img: Image.Image):
        """Return (ocr_image, display_image).

        Both share the same geometry (deskew is applied once), so bounding
        boxes from the OCR image line up exactly on the display image. The
        display image is the deskewed *colour* page — readable for a viewer —
        while the OCR image is additionally binarised for Tesseract.
        """
        arr = self._to_cv2(img)
        arr = self.deskew(arr)
        display = self._to_pil(arr)
        ocr = self._to_pil(self.enhance_page(arr))
        return ocr, display
