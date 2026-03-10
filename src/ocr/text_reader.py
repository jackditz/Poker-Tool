"""OCR module for reading text from poker table regions.

Handles stack sizes, bet amounts, pot size, and other numeric text.
"""

from __future__ import annotations

import re

import cv2
import numpy as np

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


class TextReader:
    """Reads numeric text (stack sizes, bets, pot) from cropped image regions."""

    # Tesseract config for numeric values with $ and decimal
    _NUM_CONFIG = "--psm 7 -c tessedit_char_whitelist=0123456789.$,KMkm "

    # Pattern for extracting dollar amounts like "$12.50", "1,234", "5.2K"
    _AMOUNT_PATTERN = re.compile(
        r"\$?\s*(\d[\d,]*\.?\d*)\s*([KkMm])?"
    )

    def __init__(self) -> None:
        if not _HAS_TESSERACT:
            raise RuntimeError(
                "Text reading requires pytesseract. "
                "Install with: pip install -e '.[ocr]'"
            )

    def read_amount(self, img: np.ndarray) -> float | None:
        """Read a dollar amount from an image region.

        Handles formats: "$12.50", "1,234", "5.2K", "$1.5M"
        Returns None if no valid amount is found.
        """
        text = self._ocr_text(img)
        return self._parse_amount(text)

    def read_raw_text(self, img: np.ndarray) -> str:
        """Read raw text from an image region (general purpose)."""
        return self._ocr_text(img, config="--psm 7")

    def _ocr_text(self, img: np.ndarray, config: str | None = None) -> str:
        """Preprocess image and run OCR."""
        processed = self._preprocess(img)
        cfg = config or self._NUM_CONFIG
        text = pytesseract.image_to_string(processed, config=cfg).strip()
        return text

    @staticmethod
    def _preprocess(img: np.ndarray) -> np.ndarray:
        """Preprocess for OCR: grayscale, upscale, threshold."""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        # Upscale small images
        h, w = gray.shape[:2]
        scale = max(1, 48 // min(h, w))
        if scale > 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # Adaptive threshold for varying background colors
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Add padding
        thresh = cv2.copyMakeBorder(thresh, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
        return thresh

    @classmethod
    def _parse_amount(cls, text: str) -> float | None:
        """Extract a numeric dollar amount from OCR text."""
        match = cls._AMOUNT_PATTERN.search(text)
        if not match:
            return None
        num_str = match.group(1).replace(",", "")
        try:
            value = float(num_str)
        except ValueError:
            return None

        suffix = match.group(2)
        if suffix:
            suffix = suffix.upper()
            if suffix == "K":
                value *= 1_000
            elif suffix == "M":
                value *= 1_000_000

        return value
