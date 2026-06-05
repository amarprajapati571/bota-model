from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PixelBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict[str, int]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


def normalized_roi_to_pixels(
    roi: dict[str, float], image_width: int, image_height: int
) -> PixelBox:
    x1 = _clamp(round(float(roi["x1"]) * image_width), 0, image_width)
    y1 = _clamp(round(float(roi["y1"]) * image_height), 0, image_height)
    x2 = _clamp(round(float(roi["x2"]) * image_width), 0, image_width)
    y2 = _clamp(round(float(roi["y2"]) * image_height), 0, image_height)
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return PixelBox(x1, y1, x2, y2)


def bbox_norm_to_pixels(
    bbox: dict[str, float], image_width: int, image_height: int
) -> PixelBox:
    return normalized_roi_to_pixels(bbox, image_width, image_height)


def crop_roi(image: Any, roi: dict[str, float]) -> tuple[Any, PixelBox]:
    width, height = image.size
    box = normalized_roi_to_pixels(roi, width, height)
    return image.crop((box.x1, box.y1, box.x2, box.y2)), box


def roi_debug_payload(
    rois: dict[str, dict[str, float]], image_width: int, image_height: int
) -> dict[str, Any]:
    return {
        name: {
            "normalized": dict(roi),
            "pixels": normalized_roi_to_pixels(roi, image_width, image_height).to_dict(),
        }
        for name, roi in rois.items()
    }


def save_debug_overlay(
    image_bytes: bytes,
    output_path: Path,
    rois: dict[str, dict[str, float]],
    card_payload: dict[str, list[dict[str, Any]]] | None = None,
    clock_payload: dict[str, Any] | None = None,
) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    colors = {
        "clock": (75, 186, 212),
        "timer": (75, 186, 212),
        "timer_primary": (75, 186, 212),
        "timer_secondary": (75, 186, 212),
        "player": (49, 199, 122),
        "player_cards": (49, 199, 122),
        "banker": (93, 139, 232),
        "banker_cards": (93, 139, 232),
        "result_area": (226, 184, 75),
    }

    for name, roi in rois.items():
        box = normalized_roi_to_pixels(roi, width, height)
        color = colors.get(name, (239, 244, 246))
        draw.rectangle((box.x1, box.y1, box.x2, box.y2), outline=color, width=3)
        draw.rectangle((box.x1, max(0, box.y1 - 18), box.x1 + 110, box.y1), fill=(5, 7, 8))
        draw.text((box.x1 + 4, max(0, box.y1 - 16)), name.upper(), fill=color)

    if card_payload:
        for side_key, color in (("player_cards", (49, 199, 122)), ("banker_cards", (93, 139, 232))):
            for card in card_payload.get(side_key, []):
                bbox = card.get("bbox_norm")
                if not bbox:
                    continue
                box = bbox_norm_to_pixels(bbox, width, height)
                draw.rectangle((box.x1, box.y1, box.x2, box.y2), outline=color, width=4)
                label = f"{card.get('side', '')} {card.get('slot')} {card.get('det_confidence', 0):.2f}"
                draw.rectangle((box.x1, max(0, box.y1 - 18), box.x1 + 120, box.y1), fill=(5, 7, 8))
                draw.text((box.x1 + 4, max(0, box.y1 - 16)), label, fill=(239, 244, 246))

    if clock_payload:
        text = clock_payload.get("clock_text") or clock_payload.get("text_raw") or "clock:?"
        draw.rectangle((8, 8, 260, 32), fill=(5, 7, 8))
        draw.text((12, 12), f"clock {text} conf={clock_payload.get('confidence', 0):.2f}", fill=(75, 186, 212))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, quality=88)


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))
