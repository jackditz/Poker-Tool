from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site = Column(String, nullable=False, default="bovada")
    game_type = Column(String, nullable=False)  # cash_6max, cash_9max, tournament, sng
    stakes = Column(String, nullable=True)  # "0.05/0.10", etc.
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    hands = relationship("Hand", back_populates="session", cascade="all, delete-orphan")


class Hand(Base):
    __tablename__ = "hands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    hand_number = Column(Integer, nullable=False)
    board = Column(Text, nullable=True)  # JSON array: ["Ah", "Kd", "3c"]
    pot_size = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("SessionModel", back_populates="hands")
    actions = relationship("PlayerAction", back_populates="hand", cascade="all, delete-orphan")


class PlayerAction(Base):
    __tablename__ = "player_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hand_id = Column(Integer, ForeignKey("hands.id"), nullable=False)
    seat = Column(Integer, nullable=False)  # 0-8
    street = Column(String, nullable=False)  # preflop, flop, turn, river
    action = Column(String, nullable=False)  # fold, check, call, raise, bet, all_in
    amount = Column(Float, nullable=True)
    is_voluntary = Column(Boolean, default=True)
    position = Column(String, nullable=True)  # BTN, SB, BB, UTG, MP, CO, etc.

    hand = relationship("Hand", back_populates="actions")


# Database setup — session factory stored on the app

def create_db_engine(db_url: str = "sqlite:///poker_tracker.db"):
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def create_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)
