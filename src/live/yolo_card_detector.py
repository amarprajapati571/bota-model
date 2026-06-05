from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from src.live.card_detection import DetectedCard
from src.live.roi_calibration import PixelBox, normalized_roi_to_pixels


@dataclass(frozen=True)
class YoloDetectorConfig:
    model_path: Path
    confidence: float = 0.35
    iou: float = 0.45
    imgsz: int = 960
    device: str | None = None
    card_class_names: tuple[str, ...] = ("card", "playing_card")


class YoloCardDetector:
    def __init__(self, config: YoloDetectorConfig) -> None:
        self.config = config
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is required for YOLO card detection. "
                "Install the ML requirements with: python3 -m pip install -r requirements-ml.txt"
            ) from exc

        if not config.model_path.exists():
            raise FileNotFoundError(f"YOLO model not found: {config.model_path}")
        self._model = YOLO(str(config.model_path))

    def detect(self, image_bytes: bytes, rois: dict[str, dict[str, float]]) -> dict[str, list[dict[str, Any]]]:
        try:
            from PIL import Image
        except ImportError:
            return {"player_cards": [], "banker_cards": []}

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        width, height = image.size
        roi_boxes = {
            "PLAYER": normalized_roi_to_pixels(_side_roi(rois, "player"), width, height)
            if _side_roi(rois, "player")
            else None,
            "BANKER": normalized_roi_to_pixels(_side_roi(rois, "banker"), width, height)
            if _side_roi(rois, "banker")
            else None,
        }

        predict_kwargs: dict[str, Any] = {
            "conf": self.config.confidence,
            "iou": self.config.iou,
            "imgsz": self.config.imgsz,
            "verbose": False,
        }
        if self.config.device:
            predict_kwargs["device"] = self.config.device
        results = self._model.predict(image, **predict_kwargs)

        detections = {"player_cards": [], "banker_cards": []}
        if not results:
            return detections

        names = getattr(results[0], "names", {}) or {}
        candidates: list[DetectedCard] = []
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return detections

        for raw_box in boxes:
            xyxy = _box_xyxy(raw_box)
            confidence = _box_confidence(raw_box)
            class_name = _box_class_name(raw_box, names)
            if not _is_card_class(class_name, self.config.card_class_names):
                continue
            side = _assign_side_by_center(xyxy, roi_boxes)
            if side is None:
                continue
            x1, y1, x2, y2 = xyxy
            candidates.append(
                DetectedCard(
                    side=side,
                    slot=0,
                    bbox_norm={
                        "x1": round(x1 / width, 6),
                        "y1": round(y1 / height, 6),
                        "x2": round(x2 / width, 6),
                        "y2": round(y2 / height, 6),
                    },
                    confidence=round(confidence, 4),
                )
            )

        for side, key in (("PLAYER", "player_cards"), ("BANKER", "banker_cards")):
            side_cards = [card for card in candidates if card.side == side]
            side_cards.sort(key=lambda card: card.bbox_norm["x1"])
            for slot, card in enumerate(side_cards[:3], start=1):
                detections[key].append(
                    DetectedCard(side, slot, card.bbox_norm, card.confidence).to_frontend_payload()
                )
        return detections


def build_yolo_detector(config: dict[str, Any]) -> YoloCardDetector | None:
    model_path = str(config.get("model_path") or "").strip()
    if not model_path:
        return None
    return YoloCardDetector(
        YoloDetectorConfig(
            model_path=Path(model_path),
            confidence=float(config.get("confidence", 0.35)),
            iou=float(config.get("iou", 0.45)),
            imgsz=int(config.get("imgsz", 960)),
            device=str(config["device"]) if config.get("device") else None,
            card_class_names=tuple(config.get("card_class_names", ("card", "playing_card"))),
        )
    )


def _box_xyxy(raw_box: Any) -> tuple[float, float, float, float]:
    values = raw_box.xyxy[0].tolist()
    return float(values[0]), float(values[1]), float(values[2]), float(values[3])


def _box_confidence(raw_box: Any) -> float:
    return float(raw_box.conf[0].item() if hasattr(raw_box.conf[0], "item") else raw_box.conf[0])


def _box_class_name(raw_box: Any, names: dict[int, str]) -> str:
    class_id = int(raw_box.cls[0].item() if hasattr(raw_box.cls[0], "item") else raw_box.cls[0])
    return str(names.get(class_id, class_id)).lower()


def _is_card_class(class_name: str, allowed_names: tuple[str, ...]) -> bool:
    allowed = {name.lower() for name in allowed_names}
    return not allowed or class_name.lower() in allowed


def _assign_side_by_center(
    xyxy: tuple[float, float, float, float], roi_boxes: dict[str, PixelBox | None]
) -> str | None:
    x1, y1, x2, y2 = xyxy
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    for side in ("PLAYER", "BANKER"):
        box = roi_boxes.get(side)
        if box and box.x1 <= cx <= box.x2 and box.y1 <= cy <= box.y2:
            return side
    return None


def _side_roi(rois: dict[str, dict[str, float]], side: str) -> dict[str, float] | None:
    return rois.get(f"{side}_cards") or rois.get(side)
