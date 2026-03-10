"""API endpoints for screen capture, OCR, and table reading."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.calibration.layout_config import (
    get_preset,
    list_layouts,
    load_layout,
    save_layout,
)
from src.capture.screen import Region, ScreenCapture
from src.parser.table_state import TableLayout, TableParser, TableState

router = APIRouter(prefix="/api/capture")

# ------------------------------------------------------------------
# Module-level state (managed via start/stop endpoints)
# ------------------------------------------------------------------

_capture: ScreenCapture | None = None
_parser: TableParser | None = None
_layout: TableLayout | None = None


# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class SetTableRegionRequest(BaseModel):
    x: int
    y: int
    width: int
    height: int


class LoadLayoutRequest(BaseModel):
    preset: str | None = None  # e.g. "bovada_6max"
    custom_name: str | None = None  # load saved custom layout


class SaveLayoutRequest(BaseModel):
    name: str


class TableStateResponse(BaseModel):
    seats: list[dict]
    community_cards: list[str]
    pot: float | None
    button_seat: int | None
    hero_seat: int | None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/start")
def start_capture(req: SetTableRegionRequest):
    """Initialize screen capture with the table region."""
    global _capture
    if _capture is not None:
        _capture.close()
    try:
        _capture = ScreenCapture()
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    _capture.set_table_region(Region(x=req.x, y=req.y, width=req.width, height=req.height))
    return {"status": "ok", "region": {"x": req.x, "y": req.y, "width": req.width, "height": req.height}}


@router.post("/stop")
def stop_capture():
    """Stop screen capture and release resources."""
    global _capture, _parser
    if _capture is not None:
        _capture.close()
        _capture = None
    _parser = None
    return {"status": "ok"}


@router.post("/layout")
def set_layout(req: LoadLayoutRequest):
    """Load a table layout (preset or custom saved)."""
    global _layout, _parser
    try:
        if req.preset:
            _layout = get_preset(req.preset)
        elif req.custom_name:
            _layout = load_layout(req.custom_name)
        else:
            raise HTTPException(400, "Provide either 'preset' or 'custom_name'")
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))

    try:
        _parser = TableParser(_layout)
    except RuntimeError as e:
        raise HTTPException(500, f"OCR dependencies missing: {e}")

    return {"status": "ok", "num_seats": _layout.num_seats}


@router.post("/layout/save")
def save_current_layout(req: SaveLayoutRequest):
    """Save the current layout to disk for reuse."""
    if _layout is None:
        raise HTTPException(400, "No layout loaded")
    path = save_layout(_layout, req.name)
    return {"status": "ok", "path": str(path)}


@router.get("/layouts")
def get_available_layouts():
    """List available preset and custom layouts."""
    from src.calibration.layout_config import PRESETS

    return {
        "presets": list(PRESETS.keys()),
        "custom": list_layouts(),
    }


@router.get("/read", response_model=TableStateResponse)
def read_table():
    """Capture the table and parse the current state."""
    if _capture is None:
        raise HTTPException(400, "Capture not started. POST /api/capture/start first.")
    if _parser is None:
        raise HTTPException(400, "Layout not set. POST /api/capture/layout first.")

    table_img = _capture.grab_table()
    state = _parser.parse(table_img)
    return _state_to_response(state)


@router.get("/snapshot")
def snapshot():
    """Capture and return raw table state with bet/stack ratios."""
    if _capture is None:
        raise HTTPException(400, "Capture not started.")
    if _parser is None:
        raise HTTPException(400, "Layout not set.")

    table_img = _capture.grab_table()
    state = _parser.parse(table_img)

    seats_data = []
    for s in state.seats:
        seat_dict = {
            "seat": s.seat_number,
            "status": s.status.value,
            "stack": s.stack,
            "cards": [str(c) for c in s.cards],
            "bet": s.bet,
            "position": s.position,
            "is_hero": s.is_hero,
            "bet_to_stack": state.bet_to_stack_ratio(s.seat_number),
        }
        seats_data.append(seat_dict)

    return {
        "seats": seats_data,
        "community_cards": [str(c) for c in state.community_cards],
        "pot": state.pot,
        "button_seat": state.button_seat,
        "hero_seat": state.hero_seat.seat_number if state.hero_seat else None,
    }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _state_to_response(state: TableState) -> TableStateResponse:
    seats = []
    for s in state.seats:
        seats.append({
            "seat": s.seat_number,
            "status": s.status.value,
            "stack": s.stack,
            "cards": [str(c) for c in s.cards],
            "bet": s.bet,
            "position": s.position,
            "is_hero": s.is_hero,
        })
    return TableStateResponse(
        seats=seats,
        community_cards=[str(c) for c in state.community_cards],
        pot=state.pot,
        button_seat=state.button_seat,
        hero_seat=state.hero_seat.seat_number if state.hero_seat else None,
    )
