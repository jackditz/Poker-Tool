"""Screen capture module for grabbing poker table screenshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

try:
    import mss
    import mss.tools

    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False


@dataclass
class Region:
    """A rectangular screen region (pixels)."""

    x: int
    y: int
    width: int
    height: int

    def to_mss_monitor(self) -> dict:
        return {
            "left": self.x,
            "top": self.y,
            "width": self.width,
            "height": self.height,
        }


class ScreenCapture:
    """Captures screenshots of a defined screen region.

    Usage::

        cap = ScreenCapture()
        cap.set_table_region(Region(100, 200, 800, 600))
        img = cap.grab_table()       # full table as numpy BGR array
        card_img = cap.grab_sub_region(Region(50, 400, 60, 80))  # relative to table
    """

    def __init__(self) -> None:
        if not _HAS_MSS:
            raise RuntimeError(
                "Screen capture requires the 'ocr' extras. "
                "Install with: pip install -e '.[ocr]'"
            )
        self._sct = mss.mss()
        self._table_region: Region | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_table_region(self, region: Region) -> None:
        """Set the bounding box for the poker table window."""
        self._table_region = region

    @property
    def table_region(self) -> Region | None:
        return self._table_region

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def grab_table(self) -> np.ndarray:
        """Capture the full table region and return a BGR numpy array."""
        if self._table_region is None:
            raise ValueError("Table region not set. Call set_table_region() first.")
        return self._grab(self._table_region)

    def grab_sub_region(self, rel_region: Region) -> np.ndarray:
        """Capture a sub-region *relative* to the table region."""
        if self._table_region is None:
            raise ValueError("Table region not set. Call set_table_region() first.")
        abs_region = Region(
            x=self._table_region.x + rel_region.x,
            y=self._table_region.y + rel_region.y,
            width=rel_region.width,
            height=rel_region.height,
        )
        return self._grab(abs_region)

    def grab_absolute(self, region: Region) -> np.ndarray:
        """Capture an absolute screen region."""
        return self._grab(region)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _grab(self, region: Region) -> np.ndarray:
        raw = self._sct.grab(region.to_mss_monitor())
        # mss returns BGRA — drop alpha channel to get BGR for OpenCV
        img = np.array(raw, dtype=np.uint8)
        return img[:, :, :3]

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
