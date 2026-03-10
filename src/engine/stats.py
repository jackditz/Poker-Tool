"""Poker stat calculations from recorded player actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as DBSession

from src.models.database import Hand, PlayerAction


@dataclass
class PlayerStats:
    """Computed stats for a single player/seat."""

    seat: int
    hands_played: int = 0

    # Pre-flop
    vpip_hands: int = 0  # Hands where voluntarily put money in
    pfr_hands: int = 0  # Hands where raised pre-flop
    three_bet_opportunities: int = 0
    three_bet_hands: int = 0
    faced_three_bet: int = 0
    folded_to_three_bet: int = 0

    # Post-flop
    cbet_opportunities: int = 0  # Was PFR aggressor and saw flop
    cbet_hands: int = 0  # Actually c-bet on flop
    faced_cbet: int = 0
    folded_to_cbet: int = 0

    # Aggression (post-flop only)
    postflop_bets: int = 0
    postflop_raises: int = 0
    postflop_calls: int = 0

    @property
    def vpip(self) -> float | None:
        if self.hands_played == 0:
            return None
        return self.vpip_hands / self.hands_played * 100

    @property
    def pfr(self) -> float | None:
        if self.hands_played == 0:
            return None
        return self.pfr_hands / self.hands_played * 100

    @property
    def three_bet_pct(self) -> float | None:
        if self.three_bet_opportunities == 0:
            return None
        return self.three_bet_hands / self.three_bet_opportunities * 100

    @property
    def fold_to_three_bet_pct(self) -> float | None:
        if self.faced_three_bet == 0:
            return None
        return self.folded_to_three_bet / self.faced_three_bet * 100

    @property
    def cbet_pct(self) -> float | None:
        if self.cbet_opportunities == 0:
            return None
        return self.cbet_hands / self.cbet_opportunities * 100

    @property
    def fold_to_cbet_pct(self) -> float | None:
        if self.faced_cbet == 0:
            return None
        return self.folded_to_cbet / self.faced_cbet * 100

    @property
    def aggression_factor(self) -> float | None:
        if self.postflop_calls == 0:
            return None
        return (self.postflop_bets + self.postflop_raises) / self.postflop_calls

    def to_dict(self) -> dict:
        return {
            "seat": self.seat,
            "hands_played": self.hands_played,
            "vpip": round(self.vpip, 1) if self.vpip is not None else None,
            "pfr": round(self.pfr, 1) if self.pfr is not None else None,
            "three_bet_pct": round(self.three_bet_pct, 1) if self.three_bet_pct is not None else None,
            "fold_to_three_bet": round(self.fold_to_three_bet_pct, 1) if self.fold_to_three_bet_pct is not None else None,
            "cbet_pct": round(self.cbet_pct, 1) if self.cbet_pct is not None else None,
            "fold_to_cbet": round(self.fold_to_cbet_pct, 1) if self.fold_to_cbet_pct is not None else None,
            "aggression_factor": round(self.aggression_factor, 1) if self.aggression_factor is not None else None,
        }


def compute_stats_for_seat(seat: int, hands: list[Hand]) -> PlayerStats:
    """Compute stats for a given seat across a list of hands.

    This is the core stat calculation logic. It processes the action history
    for each hand to derive pre-flop and post-flop statistics.
    """
    stats = PlayerStats(seat=seat)

    for hand in hands:
        seat_actions = [a for a in hand.actions if a.seat == seat]
        if not seat_actions:
            continue

        stats.hands_played += 1

        # Get all preflop actions for this hand (all players) to determine context
        all_preflop = [a for a in hand.actions if a.street == "preflop"]
        seat_preflop = [a for a in seat_actions if a.street == "preflop"]

        _process_preflop(stats, seat, seat_preflop, all_preflop)
        _process_postflop(stats, seat, seat_actions, hand.actions)

    return stats


def _process_preflop(
    stats: PlayerStats,
    seat: int,
    seat_preflop: list[PlayerAction],
    all_preflop: list[PlayerAction],
) -> None:
    """Process pre-flop actions for VPIP, PFR, 3-bet stats."""
    voluntary_actions = [a for a in seat_preflop if a.is_voluntary]

    # VPIP: Did this player voluntarily put money in pre-flop?
    for action in voluntary_actions:
        if action.action in ("call", "raise", "bet", "all_in"):
            stats.vpip_hands += 1
            break

    # PFR: Did this player raise pre-flop?
    for action in voluntary_actions:
        if action.action in ("raise", "bet"):
            stats.pfr_hands += 1
            break

    # 3-bet analysis: count raises in the preflop action sequence
    raise_count = 0
    for action in all_preflop:
        if action.action in ("raise", "bet") and action.is_voluntary:
            raise_count += 1

            if raise_count == 1 and action.seat != seat:
                # Someone else opened — this seat has a 3-bet opportunity
                # (if they haven't acted yet or act after this raise)
                seat_acted_after = any(
                    a for a in seat_preflop
                    if a.is_voluntary
                )
                if seat_acted_after:
                    stats.three_bet_opportunities += 1

            if raise_count == 2 and action.seat == seat:
                # This seat made the second raise = 3-bet
                stats.three_bet_hands += 1

        # Facing a 3-bet: this seat raised first, someone else 3-bet
        if raise_count == 2 and action.seat != seat:
            # Check if this seat was the original raiser
            first_raiser = None
            for a in all_preflop:
                if a.action in ("raise", "bet") and a.is_voluntary:
                    first_raiser = a.seat
                    break
            if first_raiser == seat:
                stats.faced_three_bet += 1
                # Did they fold to the 3-bet?
                for a in seat_preflop:
                    if a.action == "fold":
                        stats.folded_to_three_bet += 1
                        break
                break  # Only count once per hand


def _process_postflop(
    stats: PlayerStats,
    seat: int,
    seat_actions: list[PlayerAction],
    all_actions: list[PlayerAction],
) -> None:
    """Process post-flop actions for C-bet, aggression stats."""
    postflop_streets = ("flop", "turn", "river")

    seat_postflop = [a for a in seat_actions if a.street in postflop_streets]

    # Aggression factor components
    for action in seat_postflop:
        if action.action in ("bet", "all_in"):
            stats.postflop_bets += 1
        elif action.action == "raise":
            stats.postflop_raises += 1
        elif action.action == "call":
            stats.postflop_calls += 1

    # C-bet: Was this player the pre-flop aggressor who bet the flop?
    preflop_aggressor = _get_preflop_aggressor(all_actions)
    flop_actions_all = [a for a in all_actions if a.street == "flop"]

    if preflop_aggressor == seat and flop_actions_all:
        # This seat was PFR and saw the flop → c-bet opportunity
        stats.cbet_opportunities += 1
        seat_flop = [a for a in seat_actions if a.street == "flop"]
        for action in seat_flop:
            if action.action in ("bet", "raise", "all_in"):
                stats.cbet_hands += 1
                break

    # Fold to C-bet: opponent was PFR, bet the flop, did this seat fold?
    if preflop_aggressor is not None and preflop_aggressor != seat and flop_actions_all:
        # Check if the aggressor c-bet
        aggressor_cbet = any(
            a for a in flop_actions_all
            if a.seat == preflop_aggressor and a.action in ("bet", "raise", "all_in")
        )
        if aggressor_cbet:
            seat_flop = [a for a in seat_actions if a.street == "flop"]
            if seat_flop:  # This seat was in the hand on the flop
                stats.faced_cbet += 1
                for action in seat_flop:
                    if action.action == "fold":
                        stats.folded_to_cbet += 1
                        break


def _get_preflop_aggressor(all_actions: list[PlayerAction]) -> int | None:
    """Return the seat of the last pre-flop raiser (the PFR aggressor)."""
    last_raiser = None
    for action in all_actions:
        if action.street != "preflop":
            continue
        if action.action in ("raise", "bet") and action.is_voluntary:
            last_raiser = action.seat
    return last_raiser


def compute_all_seat_stats(session_id: int, db: "DBSession") -> dict[int, PlayerStats]:
    """Compute stats for all seats in a session."""
    hands = (
        db.query(Hand)
        .filter(Hand.session_id == session_id)
        .all()
    )

    # Find all seats that participated
    all_seats: set[int] = set()
    for hand in hands:
        for action in hand.actions:
            all_seats.add(action.seat)

    return {seat: compute_stats_for_seat(seat, hands) for seat in sorted(all_seats)}
