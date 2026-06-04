from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CardBox:
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    class_name: str = "card"


class CardDetector(Protocol):
    def detect(self, crop: object) -> tuple[CardBox, ...]:
        """Detect physical cards in a Player or Banker crop."""


class NoopCardDetector:
    def detect(self, crop: object) -> tuple[CardBox, ...]:
        return ()
