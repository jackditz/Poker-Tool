"""Tests for table state parsing, position labeling, and bet/stack ratios."""

from __future__ import annotations

import pytest

from src.ocr.card_recognizer import Card, Rank, Suit
from src.parser.table_state import (
    POSITIONS_6MAX,
    POSITIONS_9MAX,
    SeatState,
    SeatStatus,
    TableState,
)


class TestTableState:
    def _make_active_seat(self, num: int, stack: float = 100.0) -> SeatState:
        return SeatState(
            seat_number=num, status=SeatStatus.ACTIVE, stack=stack
        )

    def test_hero_detection(self):
        state = TableState(seats=[
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=100),
            SeatState(
                seat_number=1, status=SeatStatus.ACTIVE, stack=200,
                cards=[Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)],
                is_hero=True,
            ),
        ])
        hero = state.hero_seat
        assert hero is not None
        assert hero.seat_number == 1

    def test_no_hero(self):
        state = TableState(seats=[
            self._make_active_seat(0),
            self._make_active_seat(1),
        ])
        assert state.hero_seat is None

    def test_active_seats(self):
        state = TableState(seats=[
            self._make_active_seat(0),
            SeatState(seat_number=1, status=SeatStatus.EMPTY),
            self._make_active_seat(2),
            SeatState(seat_number=3, status=SeatStatus.SITTING_OUT),
        ])
        active = state.active_seats
        assert len(active) == 2
        assert active[0].seat_number == 0
        assert active[1].seat_number == 2


class TestPositionLabeling:
    def _make_6max_state(self, button_seat: int) -> TableState:
        seats = [
            SeatState(seat_number=i, status=SeatStatus.ACTIVE, stack=100.0)
            for i in range(6)
        ]
        return TableState(seats=seats, button_seat=button_seat)

    def test_6max_positions_btn_0(self):
        state = self._make_6max_state(button_seat=0)
        labels = [state.get_position_label(i) for i in range(6)]
        assert labels == ["BTN", "SB", "BB", "UTG", "MP", "CO"]

    def test_6max_positions_btn_3(self):
        state = self._make_6max_state(button_seat=3)
        # Seat 3=BTN, 4=SB, 5=BB, 0=UTG, 1=MP, 2=CO
        assert state.get_position_label(3) == "BTN"
        assert state.get_position_label(4) == "SB"
        assert state.get_position_label(5) == "BB"
        assert state.get_position_label(0) == "UTG"
        assert state.get_position_label(1) == "MP"
        assert state.get_position_label(2) == "CO"

    def test_no_button_returns_none(self):
        state = TableState(seats=[
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=100)
        ])
        assert state.get_position_label(0) is None

    def test_short_handed(self):
        """With 3 players, positions wrap correctly."""
        seats = [
            SeatState(seat_number=i, status=SeatStatus.ACTIVE, stack=100)
            for i in range(3)
        ]
        state = TableState(seats=seats, button_seat=0)
        assert state.get_position_label(0) == "BTN"
        assert state.get_position_label(1) == "SB"
        assert state.get_position_label(2) == "BB"


class TestBetToStackRatio:
    def test_ratio_calculation(self):
        seats = [
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=100.0, bet=25.0),
            SeatState(seat_number=1, status=SeatStatus.ACTIVE, stack=200.0, bet=50.0),
        ]
        state = TableState(seats=seats)
        assert state.bet_to_stack_ratio(0) == pytest.approx(0.25)
        assert state.bet_to_stack_ratio(1) == pytest.approx(0.25)

    def test_no_bet(self):
        seats = [
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=100.0, bet=None),
        ]
        state = TableState(seats=seats)
        assert state.bet_to_stack_ratio(0) is None

    def test_zero_stack(self):
        seats = [
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=0.0, bet=5.0),
        ]
        state = TableState(seats=seats)
        assert state.bet_to_stack_ratio(0) is None

    def test_missing_seat(self):
        state = TableState(seats=[])
        assert state.bet_to_stack_ratio(99) is None

    def test_half_pot_sizing(self):
        """Common sizing: 50% of stack = all-in territory."""
        seats = [
            SeatState(seat_number=0, status=SeatStatus.ACTIVE, stack=1000.0, bet=500.0),
        ]
        state = TableState(seats=seats)
        assert state.bet_to_stack_ratio(0) == pytest.approx(0.5)


class TestTextReaderParsing:
    """Test the amount parsing logic without needing Tesseract."""

    def test_parse_simple(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("$12.50") == pytest.approx(12.50)

    def test_parse_comma(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("$1,234") == pytest.approx(1234.0)

    def test_parse_k_suffix(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("5.2K") == pytest.approx(5200.0)

    def test_parse_m_suffix(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("$1.5M") == pytest.approx(1_500_000.0)

    def test_parse_no_dollar(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("250") == pytest.approx(250.0)

    def test_parse_garbage(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("no numbers here") is None

    def test_parse_empty(self):
        from src.ocr.text_reader import TextReader
        assert TextReader._parse_amount("") is None


class TestButtonDetector:
    """Test button detector's nearest-seat mapping."""

    def test_nearest_seat(self):
        from src.ocr.button_detector import ButtonDetector, Point

        positions = {
            0: Point(400, 480),
            1: Point(130, 400),
            2: Point(130, 180),
            3: Point(400, 100),
        }
        detector = ButtonDetector(seat_positions=positions)

        # Point closest to seat 0
        assert detector._nearest_seat(Point(390, 470)) == 0
        # Point closest to seat 3
        assert detector._nearest_seat(Point(410, 110)) == 3
        # Point closest to seat 1
        assert detector._nearest_seat(Point(140, 390)) == 1


class TestLayoutConfig:
    """Test layout save/load and presets."""

    def test_preset_6max(self):
        from src.calibration.layout_config import get_preset
        layout = get_preset("bovada_6max")
        assert layout.num_seats == 6
        assert len(layout.seat_card_regions) == 6
        assert len(layout.seat_stack_regions) == 6
        assert len(layout.community_card_regions) == 5
        assert layout.pot_region is not None

    def test_preset_9max(self):
        from src.calibration.layout_config import get_preset
        layout = get_preset("bovada_9max")
        assert layout.num_seats == 9
        assert len(layout.seat_card_regions) == 9

    def test_unknown_preset(self):
        from src.calibration.layout_config import get_preset
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("nonexistent")

    def test_save_and_load(self, tmp_path, monkeypatch):
        from src.calibration import layout_config
        from src.calibration.layout_config import get_preset, load_layout, save_layout

        monkeypatch.setattr(layout_config, "_CONFIG_DIR", tmp_path)

        layout = get_preset("bovada_6max")
        save_layout(layout, "test_layout")

        loaded = load_layout("test_layout")
        assert loaded.num_seats == layout.num_seats
        assert len(loaded.seat_card_regions) == len(layout.seat_card_regions)
        assert len(loaded.community_card_regions) == len(layout.community_card_regions)
