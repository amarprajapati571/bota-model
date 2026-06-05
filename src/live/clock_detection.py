from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from src.api.schemas import ClockObservation
from src.engine.clock import parse_clock_text
from src.live.roi_calibration import crop_roi


@dataclass(frozen=True)
class ClockDetection:
    observation: ClockObservation
    source: str
    crop_box_px: dict[str, int] | None = None
    debug: dict[str, Any] | None = None

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "clock_text": self.observation.parsed_time or self.observation.text_raw,
            "text_raw": self.observation.text_raw,
            "parsed_time": self.observation.parsed_time,
            "seconds_of_day": self.observation.seconds_of_day,
            "confidence": self.observation.confidence,
            "status": self.observation.status.value,
            "source": self.source,
            "crop_box_px": self.crop_box_px,
        }


def missing_clock_detection(source: str = "disabled") -> ClockDetection:
    return ClockDetection(parse_clock_text(None, 0.0), source)


def detect_clock(image_bytes: bytes, rois: dict[str, dict[str, float]]) -> ClockDetection:
    """Detect the visible clock/timer from the configured clock ROI.

    This function intentionally degrades gracefully. If pytesseract is present it
    tries OCR; otherwise it returns a missing clock observation while preserving
    crop/debug metadata for calibration.
    """

    try:
        from PIL import Image
    except ImportError:
        return ClockDetection(parse_clock_text(None, 0.0), "pil_unavailable")

    clock_roi = rois.get("clock")
    if not clock_roi:
        return ClockDetection(parse_clock_text(None, 0.0), "roi_missing")

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    crop, box = crop_roi(image, clock_roi)
    processed = preprocess_clock_crop(crop)

    text = _ocr_with_tesseract(processed)
    if text:
        observation = parse_clock_text(text, 0.72)
        if observation.parsed_time:
            return ClockDetection(
                observation,
                "tesseract",
                box.to_dict(),
                {"raw_ocr_text": text},
            )

    return ClockDetection(
        parse_clock_text(None, 0.0),
        "unreadable",
        box.to_dict(),
        {"raw_ocr_text": text},
    )


def preprocess_clock_crop(crop: Any) -> Any:
    try:
        from PIL import ImageOps
    except ImportError:
        return crop

    gray = ImageOps.grayscale(crop)
    scale = max(2, round(260 / max(gray.width, 1)))
    resized = gray.resize((gray.width * scale, gray.height * scale))
    contrasted = ImageOps.autocontrast(resized)
    return contrasted.point(lambda pixel: 255 if pixel > 128 else 0)


def _ocr_with_tesseract(image: Any) -> str | None:
    try:
        import pytesseract
    except ImportError:
        return None

    try:
        text = pytesseract.image_to_string(
            image,
            config="--psm 7 -c tessedit_char_whitelist=0123456789:",
        )
    except Exception:  # noqa: BLE001 - OCR is a best-effort fallback.
        return None
    cleaned = " ".join(text.split())
    return cleaned or None
