"""Tests for the FastAPI REST API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.deps import reset_session_factory, set_session_factory
from src.main import app
from src.models.database import Base


@pytest.fixture
def client():
    """Create a test client with an in-memory database."""
    # StaticPool ensures all connections share the same in-memory database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    set_session_factory(sessionmaker(bind=engine), force=True)

    with TestClient(app) as c:
        yield c
    reset_session_factory()


class TestSessionEndpoints:
    def test_create_session(self, client):
        res = client.post("/api/sessions", json={"game_type": "cash_6max", "stakes": "0.05/0.10"})
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == 1
        assert data["game_type"] == "cash_6max"
        assert data["stakes"] == "0.05/0.10"

    def test_list_sessions(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions", json={"game_type": "tournament"})

        res = client.get("/api/sessions")
        assert res.status_code == 200
        sessions = res.json()
        assert len(sessions) == 2

    def test_end_session(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        res = client.post("/api/sessions/1/end")
        assert res.status_code == 200
        assert "ended_at" in res.json()


class TestHandEndpoints:
    def test_create_hand(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        res = client.post("/api/sessions/1/hands")
        assert res.status_code == 200
        assert res.json()["hand_number"] == 1

    def test_sequential_hand_numbers(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        h1 = client.post("/api/sessions/1/hands").json()
        h2 = client.post("/api/sessions/1/hands").json()
        assert h1["hand_number"] == 1
        assert h2["hand_number"] == 2

    def test_update_hand_board(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions/1/hands")
        res = client.patch("/api/hands/1", json={"board": ["Ah", "Kd", "3c"], "pot_size": 25.0})
        assert res.status_code == 200

    def test_hand_not_found(self, client):
        res = client.patch("/api/hands/999", json={"pot_size": 10.0})
        assert res.status_code == 404


class TestActionEndpoints:
    def test_log_action(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions/1/hands")
        res = client.post("/api/hands/1/actions", json={
            "seat": 0,
            "street": "preflop",
            "action": "raise",
            "amount": 6.0,
            "position": "CO",
        })
        assert res.status_code == 200
        assert res.json()["action_id"] == 1

    def test_invalid_street(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions/1/hands")
        res = client.post("/api/hands/1/actions", json={
            "seat": 0,
            "street": "invalid",
            "action": "fold",
        })
        assert res.status_code == 400

    def test_invalid_action(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions/1/hands")
        res = client.post("/api/hands/1/actions", json={
            "seat": 0,
            "street": "preflop",
            "action": "invalid",
        })
        assert res.status_code == 400


class TestStatEndpoints:
    def test_get_stats_after_actions(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        client.post("/api/sessions/1/hands")

        # Seat 0 raises, seat 1 calls, seat 2 folds
        client.post("/api/hands/1/actions", json={"seat": 0, "street": "preflop", "action": "raise", "amount": 6.0})
        client.post("/api/hands/1/actions", json={"seat": 1, "street": "preflop", "action": "call", "amount": 6.0})
        client.post("/api/hands/1/actions", json={"seat": 2, "street": "preflop", "action": "fold"})

        res = client.get("/api/sessions/1/stats")
        assert res.status_code == 200
        stats = {s["seat"]: s for s in res.json()}

        assert stats[0]["vpip"] == 100.0
        assert stats[0]["pfr"] == 100.0
        assert stats[1]["vpip"] == 100.0
        assert stats[1]["pfr"] == 0.0
        assert stats[2]["vpip"] == 0.0

    def test_stats_empty_session(self, client):
        client.post("/api/sessions", json={"game_type": "cash_6max"})
        res = client.get("/api/sessions/1/stats")
        assert res.status_code == 200
        assert res.json() == []
