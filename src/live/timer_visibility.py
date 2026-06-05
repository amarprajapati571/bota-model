from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from src.live.roi_calibration import crop_roi


@dataclass(frozen=True)
class TimerVisibility:
    visible: bool
    confidence: float
    reason: str
    crop_box_px: dict[str, int] | None = None
    active_pixel_ratio: float = 0.0

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "visible": self.visible,
            "confidence": self.confidence,
            "reason": self.reason,
            "crop_box_px": self.crop_box_px,
            "active_pixel_ratio": self.active_pixel_ratio,
        }


def detect_timer_visibility(
    image_bytes: bytes,
    rois: dict[str, dict[str, float]],
    *,
    visibility_threshold: float = 0.55,
    active_pixel_ratio_full_confidence: float = 0.004,
) -> TimerVisibility:
    """Detect whether the betting countdown/timer is visible.

    This is intentionally not OCR. It checks for bright/cyan digit-like content
    in the configured timer ROI, which is enough to drive betting-vs-started
    state transitions even when OCR cannot read the numeric countdown.
    """

    try:
        from PIL import Image
    except ImportError:
        return TimerVisibility(False, 0.0, "pil_unavailable")

    roi = _timer_roi(rois)
    if not roi:
        return TimerVisibility(False, 0.0, "timer_roi_missing")

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    crop, box = crop_roi(image, roi)
    width, height = crop.size
    if width == 0 or height == 0:
        return TimerVisibility(False, 0.0, "timer_roi_empty", box.to_dict())

    pixels = crop.load()
    active = 0
    bright = 0
    cyan = 0
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            luminance = (red + green + blue) / 3
            saturation_proxy = max(red, green, blue) - min(red, green, blue)
            is_cyan_digit = blue >= 105 and green >= 90 and red <= 155 and saturation_proxy >= 35
            is_bright_digit = luminance >= 185 and saturation_proxy >= 25
            if is_cyan_digit:
                cyan += 1
            if is_bright_digit:
                bright += 1
            if is_cyan_digit or is_bright_digit:
                active += 1

    active_ratio = active / max(width * height, 1)
    confidence = max(0.0, min(1.0, active_ratio / active_pixel_ratio_full_confidence))
    visible = confidence >= visibility_threshold
    if visible:
        reason = "bright_digits" if bright >= cyan else "cyan_digits"
    elif active_ratio > 0:
        reason = "low_signal"
    else:
        reason = "hidden"
    return TimerVisibility(
        visible,
        round(confidence, 4),
        reason,
        box.to_dict(),
        round(active_ratio, 6),
    )


def _timer_roi(rois: dict[str, dict[str, float]]) -> dict[str, float] | None:
    return rois.get("timer_primary") or rois.get("timer") or rois.get("clock")
