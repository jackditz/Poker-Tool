"""Table state parser — reads a poker table screenshot and extracts game state.

Combines screen capture, card OCR, button detection, and text reading
to produce a structured snapshot of the current table state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

import numpy as np

from src.capture.screen import Region, ScreenCapture
from src.ocr.button_detector import ButtonDetector, Point
from src.ocr.card_recognizer import Card, CardRecognizer
from src.ocr.text_reader import TextReader


# ------------------------------------------------------------------
# Position labels by table size
# ------------------------------------------------------------------

POSITIONS_6MAX = ["BTN", "SB", "BB", "UTG", "MP", "CO"]
POSITIONS_9MAX = ["BTN", "SB", "BB", "UTG", "UTG+1", "UTG+2", "MP", "HJ", "CO"]


class SeatStatus(str, Enum):
    ACTIVE = "active"
    SITTING_OUT = "sitting_out"
    EMPTY = "empty"


@dataclass
class SeatState:
    """Parsed state for a single seat."""

    seat_number: int
    status: SeatStatus = SeatStatus.EMPTY
    stack: float | None = None
    cards: list[Card] = field(default_factory=list)
    bet: float | None = None
    position: str | None = None  # BTN, SB, BB, UTG, etc.
    is_hero: bool = False  # True if this is the player's seat


@dataclass
class TableState:
    """Complete snapshot of the table at a point in time."""

    seats: list[SeatState] = field(default_factory=list)
    community_cards: list[Card] = field(default_factory=list)
    pot: float | None = None
    button_seat: int | None = None

    @property
    def hero_seat(self) -> SeatState | None:
        for s in self.seats:
            if s.is_hero:
                return s
        return None

    @property
    def active_seats(self) -> list[SeatState]:
        return [s for s in self.seats if s.status == SeatStatus.ACTIVE]

    def get_position_label(self, seat_number: int) -> str | None:
        """Get the position label for a seat given the button location."""
        if self.button_seat is None:
            return None
        active = self.active_seats
        if not active:
            return None
        num_players = len(active)
        positions = POSITIONS_6MAX if num_players <= 6 else POSITIONS_9MAX

        # Build ordered list starting from button
        active_sorted = sorted(active, key=lambda s: s.seat_number)
        btn_idx = next(
            (i for i, s in enumerate(active_sorted) if s.seat_number == self.button_seat),
            None,
        )
        if btn_idx is None:
            return None

        ordered = active_sorted[btn_idx:] + active_sorted[:btn_idx]
        for i, seat in enumerate(ordered):
            if seat.seat_number == seat_number and i < len(positions):
                return positions[i]
        return None

    def bet_to_stack_ratio(self, seat_number: int) -> float | None:
        """Return the bet/stack ratio for a seat (useful for sizing reads)."""
        seat = next((s for s in self.seats if s.seat_number == seat_number), None)
        if seat is None or seat.stack is None or seat.stack == 0 or seat.bet is None:
            return None
        return seat.bet / seat.stack


@dataclass
class TableLayout:
    """Defines where each element is located relative to the table image.

    All regions are in pixels relative to the top-left of the table image.
    """

    num_seats: int = 6  # 6-max or 9-max

    # Per-seat regions (indexed by seat number 0..num_seats-1)
    seat_card_regions: dict[int, list[Region]] = field(default_factory=dict)
    seat_stack_regions: dict[int, Region] = field(default_factory=dict)
    seat_bet_regions: dict[int, Region] = field(default_factory=dict)
    seat_center_positions: dict[int, Point] = field(default_factory=dict)

    # Community cards (up to 5 regions)
    community_card_regions: list[Region] = field(default_factory=list)

    # Pot display region
    pot_region: Region | None = None


class TableParser:
    """Parses a poker table screenshot into structured TableState.

    Usage::

        layout = TableLayout(...)  # from calibration
        parser = TableParser(layout)
        state = parser.parse(table_image)
    """

    def __init__(self, layout: TableLayout) -> None:
        self._layout = layout
        self._card_recognizer = CardRecognizer()
        self._text_reader = TextReader()
        self._button_detector = ButtonDetector(
            seat_positions=layout.seat_center_positions
        )

    # ------------------------------------------------------------------
    # Main parse
    # ------------------------------------------------------------------

    def parse(self, table_img: np.ndarray) -> TableState:
        """Parse a full table screenshot into a TableState."""
        state = TableState()

        # 1. Detect button
        button = self._button_detector.detect(table_img)
        if button:
            state.button_seat = button.nearest_seat

        # 2. Parse each seat
        for seat_num in range(self._layout.num_seats):
            seat_state = self._parse_seat(table_img, seat_num)
            state.seats.append(seat_state)

        # 3. Identify hero (the seat where we can see hole cards)
        for seat in state.seats:
            if len(seat.cards) == 2:
                seat.is_hero = True
                break  # Only one hero

        # 4. Read community cards
        state.community_cards = self._read_community_cards(table_img)

        # 5. Read pot
        state.pot = self._read_pot(table_img)

        # 6. Assign position labels
        if state.button_seat is not None:
            for seat in state.seats:
                seat.position = state.get_position_label(seat.seat_number)

        return state

    # ------------------------------------------------------------------
    # Per-seat parsing
    # ------------------------------------------------------------------

    def _parse_seat(self, table_img: np.ndarray, seat_num: int) -> SeatState:
        """Parse a single seat's state."""
        seat = SeatState(seat_number=seat_num)

        # Read stack size
        stack_region = self._layout.seat_stack_regions.get(seat_num)
        if stack_region:
            stack_img = self._crop(table_img, stack_region)
            stack_val = self._text_reader.read_amount(stack_img)
            if stack_val is not None:
                seat.stack = stack_val
                seat.status = SeatStatus.ACTIVE

        # Read cards (hero will have visible cards; opponents won't)
        card_regions = self._layout.seat_card_regions.get(seat_num, [])
        for region in card_regions:
            card_img = self._crop(table_img, region)
            if self._is_card_visible(card_img):
                card = self._card_recognizer.recognize_card(card_img)
                if card:
                    seat.cards.append(card)

        # Read bet
        bet_region = self._layout.seat_bet_regions.get(seat_num)
        if bet_region:
            bet_img = self._crop(table_img, bet_region)
            bet_val = self._text_reader.read_amount(bet_img)
            if bet_val is not None:
                seat.bet = bet_val

        # Mark as active if we detected a stack or cards
        if seat.cards or (seat.stack is not None and seat.stack > 0):
            seat.status = SeatStatus.ACTIVE

        return seat

    # ------------------------------------------------------------------
    # Community cards & pot
    # ------------------------------------------------------------------

    def _read_community_cards(self, table_img: np.ndarray) -> list[Card]:
        """Read community cards from the board."""
        cards: list[Card] = []
        for region in self._layout.community_card_regions:
            card_img = self._crop(table_img, region)
            if self._is_card_visible(card_img):
                card = self._card_recognizer.recognize_card(card_img)
                if card:
                    cards.append(card)
        return cards

    def _read_pot(self, table_img: np.ndarray) -> float | None:
        """Read the pot size from the table."""
        if self._layout.pot_region is None:
            return None
        pot_img = self._crop(table_img, self._layout.pot_region)
        return self._text_reader.read_amount(pot_img)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _crop(img: np.ndarray, region: Region) -> np.ndarray:
        """Crop an image to a region."""
        return img[
            region.y : region.y + region.height,
            region.x : region.x + region.width,
        ]

    @staticmethod
    def _is_card_visible(card_img: np.ndarray) -> bool:
        """Heuristic: is this region showing a face-up card vs card back/empty?

        A face-up card has high contrast with a mostly white center.
        A card back or empty seat is more uniform.
        """
        if card_img.size == 0:
            return False
        gray = __import__("cv2").cvtColor(card_img, __import__("cv2").COLOR_BGR2GRAY)
        # A visible card has significant contrast (std dev)
        std = float(np.std(gray))
        # And a bright center region
        h, w = gray.shape
        center = gray[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4]
        mean_brightness = float(np.mean(center))
        return std > 25 and mean_brightness > 150
