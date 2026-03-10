"""Tests for card recognition and text reading (unit tests with synthetic images)."""

from __future__ import annotations

import numpy as np
import pytest

# These tests use synthetic images so they don't need a real screen or Tesseract.
# They test the parsing/logic layers rather than actual OCR accuracy.

from src.ocr.card_recognizer import Card, Rank, Suit, CardRecognizer


class TestCardModel:
    def test_card_str(self):
        c = Card(rank=Rank.ACE, suit=Suit.HEARTS)
        assert str(c) == "Ah"

    def test_card_from_string(self):
        c = Card.from_string("Td")
        assert c.rank == Rank.TEN
        assert c.suit == Suit.DIAMONDS

    def test_card_from_string_lowercase(self):
        c = Card.from_string("ks")
        assert c.rank == Rank.KING
        assert c.suit == Suit.SPADES

    def test_card_from_string_invalid(self):
        with pytest.raises(ValueError):
            Card.from_string("XX")

    def test_card_from_string_too_long(self):
        with pytest.raises(ValueError):
            Card.from_string("AhX")


class TestRankParsing:
    """Test the static rank parsing method."""

    def test_direct_ranks(self):
        parse = CardRecognizer._parse_rank
        assert parse("A") == Rank.ACE
        assert parse("K") == Rank.KING
        assert parse("Q") == Rank.QUEEN
        assert parse("J") == Rank.JACK
        assert parse("T") == Rank.TEN
        assert parse("9") == Rank.NINE
        assert parse("2") == Rank.TWO

    def test_aliases(self):
        parse = CardRecognizer._parse_rank
        assert parse("10") == Rank.TEN
        assert parse("0") == Rank.QUEEN  # common OCR misread
        assert parse("l") == Rank.JACK  # lowercase L → J
        assert parse("I") == Rank.JACK  # capital i → J

    def test_empty(self):
        assert CardRecognizer._parse_rank("") is None
        assert CardRecognizer._parse_rank("  ") is None

    def test_first_char_fallback(self):
        parse = CardRecognizer._parse_rank
        # If OCR returns "A3" it should pick "A"
        assert parse("A3") == Rank.ACE


class TestSuitDetection:
    """Test red-vs-black color detection with synthetic images."""

    def _make_solid_image(self, color_bgr: tuple, w: int = 40, h: int = 60) -> np.ndarray:
        img = np.zeros((h, w, 3), dtype=np.uint8)
        img[:] = color_bgr
        return img

    def test_red_detection(self):
        recognizer = CardRecognizer.__new__(CardRecognizer)
        # Bright red image
        red_img = self._make_solid_image((0, 0, 220))
        assert bool(recognizer._is_red(red_img)) is True

    def test_black_detection(self):
        recognizer = CardRecognizer.__new__(CardRecognizer)
        # Dark/black image
        black_img = self._make_solid_image((30, 30, 30))
        assert bool(recognizer._is_red(black_img)) is False

    def test_white_is_not_red(self):
        recognizer = CardRecognizer.__new__(CardRecognizer)
        white_img = self._make_solid_image((255, 255, 255))
        assert bool(recognizer._is_red(white_img)) is False
