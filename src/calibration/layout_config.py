"""Calibration and layout configuration for poker table recognition.

Provides preset layouts for common poker sites and the ability to
save/load custom calibration profiles.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from src.capture.screen import Region
from src.ocr.button_detector import Point
from src.parser.table_state import TableLayout


# ------------------------------------------------------------------
# Default layouts for common table sizes
# ------------------------------------------------------------------

def _bovada_6max_layout(table_width: int = 800, table_height: int = 600) -> TableLayout:
    """Default layout for Bovada/Ignition 6-max tables.

    These are approximate pixel positions that work at 800x600 resolution.
    Users should recalibrate for their actual screen resolution.
    """
    # Card dimensions (approximate)
    cw, ch = 36, 50

    # Seat positions (center of each player area) — clockwise from bottom-center
    seat_centers = {
        0: Point(400, 480),   # Bottom center (hero default)
        1: Point(130, 400),   # Left bottom
        2: Point(130, 180),   # Left top
        3: Point(400, 100),   # Top center
        4: Point(670, 180),   # Right top
        5: Point(670, 400),   # Right bottom
    }

    # Card regions: two cards per seat (only hero cards will be visible)
    seat_cards = {
        i: [
            Region(x=pos.x - cw - 2, y=pos.y - ch // 2, width=cw, height=ch),
            Region(x=pos.x + 2, y=pos.y - ch // 2, width=cw, height=ch),
        ]
        for i, pos in seat_centers.items()
    }

    # Stack regions: below each seat center
    seat_stacks = {
        i: Region(x=pos.x - 40, y=pos.y + 30, width=80, height=20)
        for i, pos in seat_centers.items()
    }

    # Bet regions: between seat and table center
    table_cx, table_cy = table_width // 2, table_height // 2
    seat_bets = {}
    for i, pos in seat_centers.items():
        bx = pos.x + (table_cx - pos.x) // 2 - 30
        by = pos.y + (table_cy - pos.y) // 2 - 10
        seat_bets[i] = Region(x=bx, y=by, width=60, height=20)

    # Community cards: 5 cards centered
    board_y = table_cy - ch // 2
    board_x_start = table_cx - (5 * cw + 4 * 4) // 2
    community = [
        Region(x=board_x_start + i * (cw + 4), y=board_y, width=cw, height=ch)
        for i in range(5)
    ]

    # Pot region
    pot = Region(x=table_cx - 50, y=table_cy - 60, width=100, height=22)

    return TableLayout(
        num_seats=6,
        seat_card_regions=seat_cards,
        seat_stack_regions=seat_stacks,
        seat_bet_regions=seat_bets,
        seat_center_positions=seat_centers,
        community_card_regions=community,
        pot_region=pot,
    )


def _bovada_9max_layout(table_width: int = 800, table_height: int = 600) -> TableLayout:
    """Default layout for Bovada/Ignition 9-max tables."""
    cw, ch = 34, 48

    seat_centers = {
        0: Point(400, 490),   # Bottom center
        1: Point(180, 460),   # Bottom left
        2: Point(80, 340),    # Left
        3: Point(80, 200),    # Upper left
        4: Point(240, 110),   # Top left
        5: Point(400, 90),    # Top center
        6: Point(560, 110),   # Top right
        7: Point(720, 200),   # Upper right
        8: Point(720, 340),   # Right
    }

    seat_cards = {
        i: [
            Region(x=pos.x - cw - 2, y=pos.y - ch // 2, width=cw, height=ch),
            Region(x=pos.x + 2, y=pos.y - ch // 2, width=cw, height=ch),
        ]
        for i, pos in seat_centers.items()
    }

    seat_stacks = {
        i: Region(x=pos.x - 40, y=pos.y + 30, width=80, height=18)
        for i, pos in seat_centers.items()
    }

    table_cx, table_cy = table_width // 2, table_height // 2
    seat_bets = {}
    for i, pos in seat_centers.items():
        bx = pos.x + (table_cx - pos.x) // 2 - 28
        by = pos.y + (table_cy - pos.y) // 2 - 9
        seat_bets[i] = Region(x=bx, y=by, width=56, height=18)

    board_y = table_cy - ch // 2
    board_x_start = table_cx - (5 * cw + 4 * 4) // 2
    community = [
        Region(x=board_x_start + i * (cw + 4), y=board_y, width=cw, height=ch)
        for i in range(5)
    ]

    pot = Region(x=table_cx - 45, y=table_cy - 55, width=90, height=20)

    return TableLayout(
        num_seats=9,
        seat_card_regions=seat_cards,
        seat_stack_regions=seat_stacks,
        seat_bet_regions=seat_bets,
        seat_center_positions=seat_centers,
        community_card_regions=community,
        pot_region=pot,
    )


# ------------------------------------------------------------------
# Preset registry
# ------------------------------------------------------------------

PRESETS: dict[str, callable] = {
    "bovada_6max": _bovada_6max_layout,
    "bovada_9max": _bovada_9max_layout,
}


def get_preset(name: str, **kwargs) -> TableLayout:
    """Get a preset table layout by name."""
    if name not in PRESETS:
        available = ", ".join(PRESETS.keys())
        raise ValueError(f"Unknown preset: {name!r}. Available: {available}")
    return PRESETS[name](**kwargs)


# ------------------------------------------------------------------
# Save / Load custom layouts
# ------------------------------------------------------------------

_CONFIG_DIR = Path.home() / ".poker-tracker" / "layouts"


def _region_to_dict(r: Region) -> dict:
    return {"x": r.x, "y": r.y, "width": r.width, "height": r.height}


def _region_from_dict(d: dict) -> Region:
    return Region(x=d["x"], y=d["y"], width=d["width"], height=d["height"])


def _point_to_dict(p: Point) -> dict:
    return {"x": p.x, "y": p.y}


def _point_from_dict(d: dict) -> Point:
    return Point(x=d["x"], y=d["y"])


def save_layout(layout: TableLayout, name: str) -> Path:
    """Save a layout to disk."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _CONFIG_DIR / f"{name}.json"

    data = {
        "num_seats": layout.num_seats,
        "seat_card_regions": {
            str(k): [_region_to_dict(r) for r in v]
            for k, v in layout.seat_card_regions.items()
        },
        "seat_stack_regions": {
            str(k): _region_to_dict(v)
            for k, v in layout.seat_stack_regions.items()
        },
        "seat_bet_regions": {
            str(k): _region_to_dict(v)
            for k, v in layout.seat_bet_regions.items()
        },
        "seat_center_positions": {
            str(k): _point_to_dict(v)
            for k, v in layout.seat_center_positions.items()
        },
        "community_card_regions": [_region_to_dict(r) for r in layout.community_card_regions],
        "pot_region": _region_to_dict(layout.pot_region) if layout.pot_region else None,
    }

    path.write_text(json.dumps(data, indent=2))
    return path


def load_layout(name: str) -> TableLayout:
    """Load a layout from disk."""
    path = _CONFIG_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Layout not found: {path}")

    data = json.loads(path.read_text())

    return TableLayout(
        num_seats=data["num_seats"],
        seat_card_regions={
            int(k): [_region_from_dict(r) for r in v]
            for k, v in data["seat_card_regions"].items()
        },
        seat_stack_regions={
            int(k): _region_from_dict(v)
            for k, v in data["seat_stack_regions"].items()
        },
        seat_bet_regions={
            int(k): _region_from_dict(v)
            for k, v in data["seat_bet_regions"].items()
        },
        seat_center_positions={
            int(k): _point_from_dict(v)
            for k, v in data["seat_center_positions"].items()
        },
        community_card_regions=[
            _region_from_dict(r) for r in data["community_card_regions"]
        ],
        pot_region=_region_from_dict(data["pot_region"]) if data["pot_region"] else None,
    )


def list_layouts() -> list[str]:
    """List saved layout names."""
    if not _CONFIG_DIR.exists():
        return []
    return [p.stem for p in _CONFIG_DIR.glob("*.json")]
