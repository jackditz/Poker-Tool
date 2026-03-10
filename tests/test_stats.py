"""Tests for the stat calculation engine."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.engine.stats import PlayerStats, compute_all_seat_stats, compute_stats_for_seat
from src.models.database import Base, Hand, PlayerAction, SessionModel


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()


def _create_session(db: Session, game_type: str = "cash_6max") -> SessionModel:
    s = SessionModel(site="bovada", game_type=game_type)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _create_hand(db: Session, session: SessionModel, hand_number: int) -> Hand:
    h = Hand(session_id=session.id, hand_number=hand_number)
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _add_action(
    db: Session,
    hand: Hand,
    seat: int,
    street: str,
    action: str,
    amount: float | None = None,
    is_voluntary: bool = True,
    position: str | None = None,
) -> PlayerAction:
    a = PlayerAction(
        hand_id=hand.id,
        seat=seat,
        street=street,
        action=action,
        amount=amount,
        is_voluntary=is_voluntary,
        position=position,
    )
    db.add(a)
    db.commit()
    return a


class TestVPIP:
    def test_call_preflop_counts_as_vpip(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="call", amount=2.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.hands_played == 1
        assert stats.vpip == 100.0

    def test_fold_preflop_not_vpip(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="fold")

        stats = compute_stats_for_seat(0, [hand])
        assert stats.hands_played == 1
        assert stats.vpip == 0.0

    def test_raise_preflop_counts_as_vpip(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.vpip == 100.0

    def test_blind_post_not_vpip(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Blind is not voluntary
        _add_action(db, hand, seat=0, street="preflop", action="call", amount=1.0, is_voluntary=False)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.vpip == 0.0

    def test_vpip_across_multiple_hands(self, db):
        session = _create_session(db)

        # Hand 1: seat 0 calls (VPIP)
        h1 = _create_hand(db, session, 1)
        _add_action(db, h1, seat=0, street="preflop", action="call", amount=2.0)

        # Hand 2: seat 0 folds (not VPIP)
        h2 = _create_hand(db, session, 2)
        _add_action(db, h2, seat=0, street="preflop", action="fold")

        # Hand 3: seat 0 raises (VPIP)
        h3 = _create_hand(db, session, 3)
        _add_action(db, h3, seat=0, street="preflop", action="raise", amount=6.0)

        # Hand 4: seat 0 folds (not VPIP)
        h4 = _create_hand(db, session, 4)
        _add_action(db, h4, seat=0, street="preflop", action="fold")

        stats = compute_stats_for_seat(0, [h1, h2, h3, h4])
        assert stats.hands_played == 4
        assert stats.vpip == 50.0  # 2/4


class TestPFR:
    def test_raise_counts_as_pfr(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.pfr == 100.0

    def test_call_not_pfr(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="call", amount=2.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.pfr == 0.0

    def test_pfr_percentage(self, db):
        session = _create_session(db)

        h1 = _create_hand(db, session, 1)
        _add_action(db, h1, seat=0, street="preflop", action="raise", amount=6.0)

        h2 = _create_hand(db, session, 2)
        _add_action(db, h2, seat=0, street="preflop", action="call", amount=2.0)

        h3 = _create_hand(db, session, 3)
        _add_action(db, h3, seat=0, street="preflop", action="fold")

        stats = compute_stats_for_seat(0, [h1, h2, h3])
        assert stats.hands_played == 3
        assert abs(stats.pfr - 33.3) < 0.1  # 1/3


class TestThreeBet:
    def test_three_bet_detected(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Seat 1 opens
        _add_action(db, hand, seat=1, street="preflop", action="raise", amount=6.0)
        # Seat 0 re-raises (3-bet)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=18.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.three_bet_opportunities >= 1
        assert stats.three_bet_hands == 1

    def test_no_three_bet_when_just_calling(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Seat 1 opens
        _add_action(db, hand, seat=1, street="preflop", action="raise", amount=6.0)
        # Seat 0 just calls
        _add_action(db, hand, seat=0, street="preflop", action="call", amount=6.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.three_bet_hands == 0


class TestCBet:
    def test_cbet_detected(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Seat 0 raises preflop (PFR)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=1, street="preflop", action="call", amount=6.0)
        # Flop: seat 0 bets (c-bet)
        _add_action(db, hand, seat=0, street="flop", action="bet", amount=8.0)

        stats = compute_stats_for_seat(0, [hand])
        assert stats.cbet_opportunities == 1
        assert stats.cbet_hands == 1
        assert stats.cbet_pct == 100.0

    def test_missed_cbet(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Seat 0 raises preflop
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=1, street="preflop", action="call", amount=6.0)
        # Flop: seat 0 checks (missed c-bet)
        _add_action(db, hand, seat=0, street="flop", action="check")

        stats = compute_stats_for_seat(0, [hand])
        assert stats.cbet_opportunities == 1
        assert stats.cbet_hands == 0
        assert stats.cbet_pct == 0.0

    def test_fold_to_cbet(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        # Seat 1 raises preflop
        _add_action(db, hand, seat=1, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=0, street="preflop", action="call", amount=6.0)
        # Flop: seat 1 c-bets, seat 0 folds
        _add_action(db, hand, seat=1, street="flop", action="bet", amount=8.0)
        _add_action(db, hand, seat=0, street="flop", action="fold")

        stats = compute_stats_for_seat(0, [hand])
        assert stats.faced_cbet == 1
        assert stats.folded_to_cbet == 1
        assert stats.fold_to_cbet_pct == 100.0


class TestAggression:
    def test_aggression_factor(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=1, street="preflop", action="call", amount=6.0)
        # Flop: bet
        _add_action(db, hand, seat=0, street="flop", action="bet", amount=8.0)
        _add_action(db, hand, seat=1, street="flop", action="call", amount=8.0)
        # Turn: bet again
        _add_action(db, hand, seat=0, street="turn", action="bet", amount=16.0)
        _add_action(db, hand, seat=1, street="turn", action="raise", amount=40.0)
        # Seat 0 calls the raise
        _add_action(db, hand, seat=0, street="turn", action="call", amount=40.0)

        stats = compute_stats_for_seat(0, [hand])
        # Seat 0 postflop: 2 bets, 0 raises, 1 call → AF = 2/1 = 2.0
        assert stats.aggression_factor == 2.0

    def test_no_calls_af_is_none(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=0, street="flop", action="bet", amount=8.0)

        stats = compute_stats_for_seat(0, [hand])
        # No postflop calls → AF undefined
        assert stats.aggression_factor is None


class TestPlayerStatsDict:
    def test_no_data_returns_nulls(self):
        stats = PlayerStats(seat=0)
        d = stats.to_dict()
        assert d["hands_played"] == 0
        assert d["vpip"] is None
        assert d["pfr"] is None
        assert d["aggression_factor"] is None


class TestComputeAllSeatStats:
    def test_returns_stats_for_all_active_seats(self, db):
        session = _create_session(db)
        hand = _create_hand(db, session, 1)
        _add_action(db, hand, seat=0, street="preflop", action="raise", amount=6.0)
        _add_action(db, hand, seat=1, street="preflop", action="call", amount=6.0)
        _add_action(db, hand, seat=2, street="preflop", action="fold")

        all_stats = compute_all_seat_stats(session.id, db)
        assert 0 in all_stats
        assert 1 in all_stats
        assert 2 in all_stats
        assert all_stats[0].vpip == 100.0
        assert all_stats[1].vpip == 100.0
        assert all_stats[2].vpip == 0.0
