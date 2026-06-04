from __future__ import annotations

from typing import Protocol

from src.api.schemas import ClockObservation
from src.engine.clock import parse_clock_text


class ClockOCR(Protocol):
    def predict(self, crop: object) -> ClockObservation:
        """Return a parsed clock observation for a cropped clock image."""


class TextClockOCR:
    """Development OCR adapter that treats the crop as already-recognized text."""

    def predict(self, crop: object) -> ClockObservation:
        return parse_clock_text(str(crop), confidence=1.0)
