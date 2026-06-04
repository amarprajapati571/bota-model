from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.api.schemas import Visibility


@dataclass(frozen=True)
class CardClassification:
    rank: str | None
    suit: str | None
    confidence: float
    visibility: Visibility = Visibility.VISIBLE


class CardClassifier(Protocol):
    def predict(self, crop: object) -> CardClassification:
        """Classify rank, suit, and visibility from a detected card crop."""


class UnknownCardClassifier:
    def predict(self, crop: object) -> CardClassification:
        return CardClassification(None, None, 0.0, Visibility.UNKNOWN)
