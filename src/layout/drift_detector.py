from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriftObservation:
    layout_confidence: float
    anchor_shift_px: float
    drift_detected: bool


def detect_layout_drift(anchor_shift_px: float, max_anchor_shift_px: float = 15.0) -> DriftObservation:
    drift = anchor_shift_px > max_anchor_shift_px
    confidence = max(0.0, min(1.0, 1.0 - anchor_shift_px / max_anchor_shift_px))
    return DriftObservation(confidence, anchor_shift_px, drift)
