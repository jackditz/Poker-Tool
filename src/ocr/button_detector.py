"""Dealer button detection for determining seat positions.

The button (dealer) marker is a distinctive circular element on the table.
This module detects its position and maps it to the nearest seat.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Point:
    x: int
    y: int


@dataclass
class ButtonDetection:
    """Result of button detection."""

    center: Point
    radius: int
    confidence: float  # 0.0 – 1.0
    nearest_seat: int | None = None


class ButtonDetector:
    """Detects the dealer button on a poker table screenshot.

    The button is identified by:
    1. Color filtering (white/yellow circular marker)
    2. Hough circle detection
    3. Optional template matching for "D" or "DEALER" text

    After detection, the button position is mapped to the nearest
    seat based on a configured seat layout.
    """

    # HSV ranges for the white/yellow dealer button
    BUTTON_WHITE_LOWER = np.array([0, 0, 200])
    BUTTON_WHITE_UPPER = np.array([180, 40, 255])
    BUTTON_YELLOW_LOWER = np.array([20, 100, 150])
    BUTTON_YELLOW_UPPER = np.array([35, 255, 255])

    # Expected button radius range (pixels) — tuned per resolution
    MIN_RADIUS = 8
    MAX_RADIUS = 30

    def __init__(self, seat_positions: dict[int, Point] | None = None) -> None:
        """
        Args:
            seat_positions: Mapping of seat number → center point (relative
                to table image). Used to map detected button to nearest seat.
        """
        self._seat_positions = seat_positions or {}

    def set_seat_positions(self, positions: dict[int, Point]) -> None:
        self._seat_positions = positions

    def detect(self, table_img: np.ndarray) -> ButtonDetection | None:
        """Detect the dealer button in a table screenshot.

        Returns the best ButtonDetection or None if not found.
        """
        candidates = self._find_button_candidates(table_img)
        if not candidates:
            return None

        # Pick the candidate with highest confidence
        best = max(candidates, key=lambda d: d.confidence)

        # Map to nearest seat
        if self._seat_positions:
            best.nearest_seat = self._nearest_seat(best.center)

        return best

    def _find_button_candidates(self, img: np.ndarray) -> list[ButtonDetection]:
        """Find circular button candidates via color filtering + Hough circles."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Mask for white and yellow button variants
        white_mask = cv2.inRange(hsv, self.BUTTON_WHITE_LOWER, self.BUTTON_WHITE_UPPER)
        yellow_mask = cv2.inRange(hsv, self.BUTTON_YELLOW_LOWER, self.BUTTON_YELLOW_UPPER)
        combined = cv2.bitwise_or(white_mask, yellow_mask)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)

        # Hough circle detection
        circles = cv2.HoughCircles(
            combined,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=30,
            param1=50,
            param2=20,
            minRadius=self.MIN_RADIUS,
            maxRadius=self.MAX_RADIUS,
        )

        results: list[ButtonDetection] = []
        if circles is None:
            return results

        for circle in np.round(circles[0]).astype(int):
            cx, cy, r = circle
            # Confidence based on how circular/white the region is
            confidence = self._score_button(img, combined, cx, cy, r)
            if confidence > 0.3:
                results.append(
                    ButtonDetection(
                        center=Point(cx, cy),
                        radius=int(r),
                        confidence=confidence,
                    )
                )

        return results

    @staticmethod
    def _score_button(
        img: np.ndarray,
        mask: np.ndarray,
        cx: int,
        cy: int,
        r: int,
    ) -> float:
        """Score how likely a detected circle is the dealer button.

        Combines: ratio of white/yellow pixels inside circle,
        and presence of text-like features ("D").
        """
        h, w = mask.shape[:2]
        # Create circle mask
        circle_mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(circle_mask, (cx, cy), r, 255, -1)

        # Ratio of color-matching pixels inside the circle
        intersection = cv2.bitwise_and(mask, circle_mask)
        circle_pixels = np.count_nonzero(circle_mask)
        if circle_pixels == 0:
            return 0.0
        fill_ratio = np.count_nonzero(intersection) / circle_pixels

        # Check for "D" text inside the circle region
        y1 = max(0, cy - r)
        y2 = min(h, cy + r)
        x1 = max(0, cx - r)
        x2 = min(w, cx + r)
        roi = img[y1:y2, x1:x2]

        text_score = 0.0
        if roi.size > 0:
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            # A "D" character typically has 1 contour with moderate solidity
            for cnt in contours:
                area = cv2.contourArea(cnt)
                roi_area = roi.shape[0] * roi.shape[1]
                if 0.05 < area / roi_area < 0.6:
                    text_score = 0.3
                    break

        return min(1.0, fill_ratio * 0.7 + text_score)

    def _nearest_seat(self, point: Point) -> int:
        """Return the seat number closest to the given point."""
        best_seat = 0
        best_dist = float("inf")
        for seat, pos in self._seat_positions.items():
            dist = ((point.x - pos.x) ** 2 + (point.y - pos.y) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_seat = seat
        return best_seat
