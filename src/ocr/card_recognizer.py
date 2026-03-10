"""Card recognition via image processing and OCR.

Cards are identified by a combination of:
1. Color detection (red/black) to narrow suit
2. Tesseract OCR on the rank region
3. Suit symbol shape matching via contour analysis
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import cv2
import numpy as np

try:
    import pytesseract

    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


class Suit(str, Enum):
    HEARTS = "h"
    DIAMONDS = "d"
    CLUBS = "c"
    SPADES = "s"


class Rank(str, Enum):
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "T"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"


# Common OCR misreads → correct rank
_RANK_ALIASES: dict[str, str] = {
    "10": "T",
    "1": "A",
    "0": "Q",
    "O": "Q",
    "l": "J",
    "I": "J",
    "|": "J",
}

VALID_RANKS = {r.value for r in Rank}


@dataclass
class Card:
    rank: Rank
    suit: Suit

    def __str__(self) -> str:
        return f"{self.rank.value}{self.suit.value}"

    @classmethod
    def from_string(cls, s: str) -> "Card":
        """Parse 'Ah', 'Td', etc."""
        if len(s) != 2:
            raise ValueError(f"Invalid card string: {s!r}")
        return cls(rank=Rank(s[0].upper()), suit=Suit(s[1].lower()))


class CardRecognizer:
    """Recognizes playing cards from cropped card images.

    Each card image should be tightly cropped around a single card.
    The recognizer uses a two-step process:
    1. Read the rank from the top-left corner via OCR
    2. Determine the suit from color (red vs black) and shape analysis
    """

    # HSV ranges for red detection (hearts/diamonds)
    RED_LOWER_1 = np.array([0, 80, 80])
    RED_UPPER_1 = np.array([10, 255, 255])
    RED_LOWER_2 = np.array([160, 80, 80])
    RED_UPPER_2 = np.array([180, 255, 255])

    # Tesseract config for single character recognition
    _TESS_CONFIG = "--psm 10 -c tessedit_char_whitelist=0123456789AKQJT"

    def __init__(self) -> None:
        if not _HAS_TESSERACT:
            raise RuntimeError(
                "Card recognition requires pytesseract. "
                "Install with: pip install -e '.[ocr]'"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize_card(self, card_img: np.ndarray) -> Card | None:
        """Attempt to recognize a single card from a cropped image.

        Returns None if recognition fails.
        """
        rank = self._detect_rank(card_img)
        suit = self._detect_suit(card_img)
        if rank is None or suit is None:
            return None
        return Card(rank=rank, suit=suit)

    def recognize_cards(self, card_images: Sequence[np.ndarray]) -> list[Card | None]:
        """Recognize multiple card images."""
        return [self.recognize_card(img) for img in card_images]

    # ------------------------------------------------------------------
    # Rank detection
    # ------------------------------------------------------------------

    def _detect_rank(self, card_img: np.ndarray) -> Rank | None:
        """Read the rank character from the top-left corner."""
        h, w = card_img.shape[:2]
        # Rank is typically in the top-left ~30% width, ~35% height
        rank_region = card_img[: int(h * 0.35), : int(w * 0.30)]

        # Preprocess: grayscale → threshold → invert for black text on white
        gray = cv2.cvtColor(rank_region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Resize up for better OCR accuracy
        scale = max(1, 64 // max(thresh.shape))
        if scale > 1:
            thresh = cv2.resize(
                thresh, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

        # Add border padding
        thresh = cv2.copyMakeBorder(thresh, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=0)

        text = pytesseract.image_to_string(thresh, config=self._TESS_CONFIG).strip()
        return self._parse_rank(text)

    @staticmethod
    def _parse_rank(text: str) -> Rank | None:
        """Normalize OCR output to a valid Rank."""
        raw = text.strip()
        if not raw:
            return None
        # Check aliases on raw text first (before uppercasing, to catch 'l' → 'J')
        corrected = _RANK_ALIASES.get(raw)
        if corrected and corrected in VALID_RANKS:
            return Rank(corrected)
        text = raw.upper()
        # Direct match
        if text in VALID_RANKS:
            return Rank(text)
        # Check aliases on uppercased text
        corrected = _RANK_ALIASES.get(text)
        if corrected and corrected in VALID_RANKS:
            return Rank(corrected)
        # Try first character (raw first for alias, then upper)
        raw_ch = raw[0]
        corrected = _RANK_ALIASES.get(raw_ch)
        if corrected and corrected in VALID_RANKS:
            return Rank(corrected)
        ch = text[0]
        if ch in VALID_RANKS:
            return Rank(ch)
        corrected = _RANK_ALIASES.get(ch)
        if corrected and corrected in VALID_RANKS:
            return Rank(corrected)
        return None

    # ------------------------------------------------------------------
    # Suit detection
    # ------------------------------------------------------------------

    def _detect_suit(self, card_img: np.ndarray) -> Suit | None:
        """Determine suit via color analysis and contour shape.

        Step 1: Is the card red or black?
        Step 2: For red → hearts vs diamonds via contour convexity
                For black → spades vs clubs via contour convexity
        """
        is_red = self._is_red(card_img)
        h, w = card_img.shape[:2]

        # Suit pip is typically below the rank, in the top-left area
        suit_region = card_img[int(h * 0.30) : int(h * 0.55), : int(w * 0.30)]

        if is_red:
            return self._classify_red_suit(suit_region)
        return self._classify_black_suit(suit_region)

    def _is_red(self, card_img: np.ndarray) -> bool:
        """Check if the card symbols are red (hearts/diamonds) or black."""
        hsv = cv2.cvtColor(card_img, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self.RED_LOWER_1, self.RED_UPPER_1)
        mask2 = cv2.inRange(hsv, self.RED_LOWER_2, self.RED_UPPER_2)
        red_mask = cv2.bitwise_or(mask1, mask2)
        red_ratio = np.count_nonzero(red_mask) / red_mask.size
        return red_ratio > 0.03  # More than 3% red pixels → red suit

    def _classify_red_suit(self, suit_region: np.ndarray) -> Suit:
        """Distinguish hearts from diamonds using contour shape.

        Diamonds have high convexity (close to polygon), hearts are more
        irregular with the cleft at top.
        """
        solidity = self._get_largest_contour_solidity(suit_region)
        if solidity is None:
            return Suit.HEARTS  # Default fallback
        # Diamonds are very convex (solidity > 0.9), hearts less so
        return Suit.DIAMONDS if solidity > 0.85 else Suit.HEARTS

    def _classify_black_suit(self, suit_region: np.ndarray) -> Suit:
        """Distinguish spades from clubs using contour shape.

        Clubs have lower solidity due to the three-lobed shape.
        Spades are more pointed/solid.
        """
        solidity = self._get_largest_contour_solidity(suit_region)
        if solidity is None:
            return Suit.SPADES  # Default fallback
        # Clubs have lower solidity than spades due to lobes
        return Suit.CLUBS if solidity < 0.78 else Suit.SPADES

    @staticmethod
    def _get_largest_contour_solidity(region: np.ndarray) -> float | None:
        """Find the largest contour in a region and return its solidity.

        Solidity = contour area / convex hull area.
        """
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < 20:
            return None
        hull = cv2.convexHull(largest)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0:
            return None
        return area / hull_area
