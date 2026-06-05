from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any


@dataclass(frozen=True)
class DetectedCard:
    side: str
    slot: int
    bbox_norm: dict[str, float]
    confidence: float

    def to_frontend_payload(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "rank": None,
            "suit": None,
            "card_code": None,
            "bbox_norm": self.bbox_norm,
            "det_confidence": self.confidence,
            "rank_confidence": 0.0,
            "suit_confidence": 0.0,
            "stable": False,
        }


def detect_card_boxes(image_bytes: bytes, rois: dict[str, dict[str, float]]) -> dict[str, list[dict[str, Any]]]:
    """Detect bright card-like rectangles in player/banker ROIs.

    This is a baseline computer-vision detector. It is not a rank/suit model and
    should be replaced by the trained detector/classifier for production output.
    """

    try:
        from PIL import Image
    except ImportError:
        return {"player_cards": [], "banker_cards": []}

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    width, height = image.size

    try:
        import numpy as np

        frame = np.array(image)
        player = _detect_side_opencv(frame, width, height, rois.get("player"), "PLAYER")
        banker = _detect_side_opencv(frame, width, height, rois.get("banker"), "BANKER")
    except ImportError:
        player = _detect_side_pillow(image, width, height, rois.get("player"), "PLAYER")
        banker = _detect_side_pillow(image, width, height, rois.get("banker"), "BANKER")

    return {
        "player_cards": [card.to_frontend_payload() for card in player],
        "banker_cards": [card.to_frontend_payload() for card in banker],
    }


def _detect_side_opencv(
    frame, width: int, height: int, roi: dict[str, float] | None, side: str
) -> list[DetectedCard]:
    if not roi:
        return []

    import cv2
    import numpy as np

    x1 = max(0, int(float(roi["x1"]) * width))
    y1 = max(0, int(float(roi["y1"]) * height))
    x2 = min(width, int(float(roi["x2"]) * width))
    y2 = min(height, int(float(roi["y2"]) * height))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return []

    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    # Cards are usually low-saturation and bright compared to green felt.
    mask = cv2.inRange(hsv, np.array([0, 0, 115]), np.array([180, 95, 255]))
    kernel = np.ones((3, 3), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_width = max(1, x2 - x1)
    roi_height = max(1, y2 - y1)
    min_area = roi_width * roi_height * 0.008
    max_area = roi_width * roi_height * 0.20

    candidates: list[tuple[int, int, int, int, float]] = []
    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        area = cw * ch
        if area < min_area or area > max_area:
            continue
        aspect = cw / max(ch, 1)
        if not 0.35 <= aspect <= 1.35:
            continue
        if cw < roi_width * 0.035 or ch < roi_height * 0.18:
            continue

        fill_ratio = cv2.contourArea(contour) / max(area, 1)
        if fill_ratio < 0.28:
            continue
        candidates.append((cx, cy, cw, ch, min(0.95, max(0.45, fill_ratio))))

    candidates = _dedupe_boxes(candidates)
    candidates.sort(key=lambda item: item[0])

    cards: list[DetectedCard] = []
    for slot, (cx, cy, cw, ch, confidence) in enumerate(candidates[:3], start=1):
        abs_x1 = x1 + cx
        abs_y1 = y1 + cy
        abs_x2 = x1 + cx + cw
        abs_y2 = y1 + cy + ch
        cards.append(
            DetectedCard(
                side=side,
                slot=slot,
                bbox_norm={
                    "x1": round(abs_x1 / width, 6),
                    "y1": round(abs_y1 / height, 6),
                    "x2": round(abs_x2 / width, 6),
                    "y2": round(abs_y2 / height, 6),
                },
                confidence=round(confidence, 4),
            )
        )
    return cards


def _detect_side_pillow(
    image, width: int, height: int, roi: dict[str, float] | None, side: str
) -> list[DetectedCard]:
    if not roi:
        return []

    x1 = max(0, int(float(roi["x1"]) * width))
    y1 = max(0, int(float(roi["y1"]) * height))
    x2 = min(width, int(float(roi["x2"]) * width))
    y2 = min(height, int(float(roi["y2"]) * height))
    crop = image.crop((x1, y1, x2, y2)).convert("RGB")
    crop_width, crop_height = crop.size
    if crop_width == 0 or crop_height == 0:
        return []

    pixels = crop.load()
    mask = [[False for _ in range(crop_width)] for _ in range(crop_height)]
    for y in range(crop_height):
        for x in range(crop_width):
            red, green, blue = pixels[x, y]
            bright = (red + green + blue) / 3
            saturation_proxy = max(red, green, blue) - min(red, green, blue)
            mask[y][x] = bright >= 135 and saturation_proxy <= 100

    visited = [[False for _ in range(crop_width)] for _ in range(crop_height)]
    roi_area = crop_width * crop_height
    min_area = roi_area * 0.008
    max_area = roi_area * 0.20
    boxes: list[tuple[int, int, int, int, float]] = []

    for y in range(crop_height):
        for x in range(crop_width):
            if visited[y][x] or not mask[y][x]:
                continue
            component = _flood_fill(mask, visited, x, y)
            if not component:
                continue
            xs = [point[0] for point in component]
            ys = [point[1] for point in component]
            bx1, by1, bx2, by2 = min(xs), min(ys), max(xs) + 1, max(ys) + 1
            bw, bh = bx2 - bx1, by2 - by1
            area = bw * bh
            if area < min_area or area > max_area:
                continue
            aspect = bw / max(bh, 1)
            if not 0.35 <= aspect <= 1.35:
                continue
            if bw < crop_width * 0.035 or bh < crop_height * 0.18:
                continue
            fill_ratio = len(component) / max(area, 1)
            if fill_ratio < 0.28:
                continue
            boxes.append((bx1, by1, bw, bh, min(0.9, max(0.45, fill_ratio))))

    boxes = _dedupe_boxes(boxes)
    boxes.sort(key=lambda item: item[0])

    cards: list[DetectedCard] = []
    for slot, (bx, by, bw, bh, confidence) in enumerate(boxes[:3], start=1):
        cards.append(
            DetectedCard(
                side=side,
                slot=slot,
                bbox_norm={
                    "x1": round((x1 + bx) / width, 6),
                    "y1": round((y1 + by) / height, 6),
                    "x2": round((x1 + bx + bw) / width, 6),
                    "y2": round((y1 + by + bh) / height, 6),
                },
                confidence=round(confidence, 4),
            )
        )
    return cards


def _flood_fill(
    mask: list[list[bool]], visited: list[list[bool]], start_x: int, start_y: int
) -> list[tuple[int, int]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    stack = [(start_x, start_y)]
    component: list[tuple[int, int]] = []
    visited[start_y][start_x] = True

    while stack:
        x, y = stack.pop()
        component.append((x, y))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if visited[ny][nx] or not mask[ny][nx]:
                continue
            visited[ny][nx] = True
            stack.append((nx, ny))
    return component


def _dedupe_boxes(boxes: list[tuple[int, int, int, int, float]]) -> list[tuple[int, int, int, int, float]]:
    kept: list[tuple[int, int, int, int, float]] = []
    for box in sorted(boxes, key=lambda item: item[2] * item[3], reverse=True):
        if all(_iou(box, existing) < 0.35 for existing in kept):
            kept.append(box)
    return kept


def _iou(a: tuple[int, int, int, int, float], b: tuple[int, int, int, int, float]) -> float:
    ax1, ay1, aw, ah, _ = a
    bx1, by1, bw, bh, _ = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0
