"""FastAPI REST endpoints for session management, action logging, and stat queries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from src.deps import get_db
from src.engine.stats import compute_all_seat_stats
from src.models.database import Hand, PlayerAction, SessionModel

router = APIRouter(prefix="/api")


# --- Request/Response schemas ---


class CreateSessionRequest(BaseModel):
    site: str = "bovada"
    game_type: str  # cash_6max, cash_9max, tournament, sng
    stakes: str | None = None


class CreateSessionResponse(BaseModel):
    id: int
    site: str
    game_type: str
    stakes: str | None
    started_at: str


class NewHandRequest(BaseModel):
    """Start a new hand in the session."""
    pass


class NewHandResponse(BaseModel):
    id: int
    hand_number: int


class LogActionRequest(BaseModel):
    seat: int
    street: str  # preflop, flop, turn, river
    action: str  # fold, check, call, raise, bet, all_in
    amount: float | None = None
    is_voluntary: bool = True
    position: str | None = None


class UpdateHandRequest(BaseModel):
    board: list[str] | None = None  # ["Ah", "Kd", "3c"]
    pot_size: float | None = None


class SeatStatResponse(BaseModel):
    seat: int
    hands_played: int
    vpip: float | None
    pfr: float | None
    three_bet_pct: float | None
    fold_to_three_bet: float | None
    cbet_pct: float | None
    fold_to_cbet: float | None
    aggression_factor: float | None


DB = Annotated[DBSession, Depends(get_db)]


# --- Session endpoints ---


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(req: CreateSessionRequest, db: DB):
    session = SessionModel(site=req.site, game_type=req.game_type, stakes=req.stakes)
    db.add(session)
    db.commit()
    db.refresh(session)
    return CreateSessionResponse(
        id=session.id,
        site=session.site,
        game_type=session.game_type,
        stakes=session.stakes,
        started_at=session.started_at.isoformat(),
    )


@router.post("/sessions/{session_id}/end")
def end_session(session_id: int, db: DB):
    session = db.query(SessionModel).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "ended_at": session.ended_at.isoformat()}


@router.get("/sessions")
def list_sessions(db: DB):
    sessions = db.query(SessionModel).order_by(SessionModel.started_at.desc()).all()
    return [
        {
            "id": s.id,
            "site": s.site,
            "game_type": s.game_type,
            "stakes": s.stakes,
            "started_at": s.started_at.isoformat(),
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "hand_count": len(s.hands),
        }
        for s in sessions
    ]


# --- Hand endpoints ---


@router.post("/sessions/{session_id}/hands", response_model=NewHandResponse)
def new_hand(session_id: int, db: DB):
    session = db.query(SessionModel).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    hand_number = len(session.hands) + 1
    hand = Hand(session_id=session_id, hand_number=hand_number)
    db.add(hand)
    db.commit()
    db.refresh(hand)
    return NewHandResponse(id=hand.id, hand_number=hand.hand_number)


@router.patch("/hands/{hand_id}")
def update_hand(hand_id: int, req: UpdateHandRequest, db: DB):
    hand = db.query(Hand).get(hand_id)
    if not hand:
        raise HTTPException(404, "Hand not found")
    if req.board is not None:
        hand.board = json.dumps(req.board)
    if req.pot_size is not None:
        hand.pot_size = req.pot_size
    db.commit()
    return {"status": "ok"}


# --- Action endpoints ---


@router.post("/hands/{hand_id}/actions")
def log_action(hand_id: int, req: LogActionRequest, db: DB):
    hand = db.query(Hand).get(hand_id)
    if not hand:
        raise HTTPException(404, "Hand not found")

    valid_streets = ("preflop", "flop", "turn", "river")
    if req.street not in valid_streets:
        raise HTTPException(400, f"Invalid street: {req.street}. Must be one of {valid_streets}")

    valid_actions = ("fold", "check", "call", "raise", "bet", "all_in")
    if req.action not in valid_actions:
        raise HTTPException(400, f"Invalid action: {req.action}. Must be one of {valid_actions}")

    action = PlayerAction(
        hand_id=hand_id,
        seat=req.seat,
        street=req.street,
        action=req.action,
        amount=req.amount,
        is_voluntary=req.is_voluntary,
        position=req.position,
    )
    db.add(action)
    db.commit()
    return {"status": "ok", "action_id": action.id}


# --- Stat endpoints ---


@router.get("/sessions/{session_id}/stats", response_model=list[SeatStatResponse])
def get_session_stats(session_id: int, db: DB):
    session = db.query(SessionModel).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    seat_stats = compute_all_seat_stats(session_id, db)
    return [stats.to_dict() for stats in seat_stats.values()]


@router.get("/sessions/{session_id}/hands")
def list_hands(session_id: int, db: DB):
    hands = (
        db.query(Hand)
        .filter(Hand.session_id == session_id)
        .order_by(Hand.hand_number.desc())
        .all()
    )
    return [
        {
            "id": h.id,
            "hand_number": h.hand_number,
            "board": json.loads(h.board) if h.board else None,
            "pot_size": h.pot_size,
            "timestamp": h.timestamp.isoformat(),
            "action_count": len(h.actions),
        }
        for h in hands
    ]
