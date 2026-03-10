"""WebSocket endpoint for pushing live HUD stat updates to the frontend."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    pass

router = APIRouter()

# Connected HUD clients
_clients: set[WebSocket] = set()


@router.websocket("/ws/hud")
async def hud_websocket(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)


async def broadcast_stats(stats: dict):
    """Push updated stats to all connected HUD clients."""
    if not _clients:
        return
    message = json.dumps({"type": "stats_update", "data": stats})
    disconnected = set()
    for client in _clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    _clients -= disconnected
