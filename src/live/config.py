from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LiveConfig:
    table_id: str
    stream_id: str
    camera_id: str
    source_type: str
    source_url: str
    viewport_width: int
    viewport_height: int
    raw_frame_width: int
    raw_frame_height: int
    wait_after_load_ms: int
    capture_fps: float
    evidence_dir: Path
    save_latest_frame: bool
    save_roi_crops: bool
    playback: dict[str, Any]
    ws_url: str
    rois: dict[str, dict[str, float]]
    clock_ocr_enabled: bool
    card_recognition_enabled: bool
    card_detector_backend: str
    yolo_card_detector: dict[str, Any]
    debug_sample_every: int
    card_hold_frames: int
    card_confirm_frames: int
    card_min_confidence: float
    visual_stable_frames: int
    empty_reset_frames: int
    clock_ocr_interval_frames: int
    timer_visibility_threshold: float
    timer_hidden_confirm_frames: int
    timer_visible_confirm_frames: int
    round_reset_delay_ms: int


def load_live_config(path: str | Path) -> LiveConfig:
    payload = _load_mapping(Path(path))
    table = payload.get("table", {})
    source = payload.get("source", {})
    viewport = source.get("viewport", {})
    capture = payload.get("capture", {})
    frontend = payload.get("frontend", {})
    overlay = payload.get("overlay_config", {})
    models = payload.get("models", {})
    debug = payload.get("debug", {})
    temporal = payload.get("temporal", {})

    return LiveConfig(
        table_id=str(table.get("table_id", "MD3212")),
        stream_id=str(table.get("stream_id", "stream_MD3212_live")),
        camera_id=str(table.get("camera_id", "cam-01")),
        source_type=str(source.get("type", "browser_page")),
        source_url=str(source.get("url", "")),
        viewport_width=int(viewport.get("width", 1466)),
        viewport_height=int(viewport.get("height", 746)),
        raw_frame_width=int(source.get("raw_frame_width", viewport.get("width", 1466))),
        raw_frame_height=int(source.get("raw_frame_height", viewport.get("height", 746))),
        wait_after_load_ms=int(source.get("wait_after_load_ms", 2500)),
        capture_fps=float(capture.get("fps", 1)),
        evidence_dir=Path(capture.get("evidence_dir", "evidence/live/MD3212")),
        save_latest_frame=bool(capture.get("save_latest_frame", True)),
        save_roi_crops=bool(capture.get("save_roi_crops", True)),
        playback=dict(payload.get("playback", {})),
        ws_url=str(frontend.get("ws_url", "")),
        rois=dict(overlay.get("rois", {})),
        clock_ocr_enabled=bool(models.get("clock_ocr_enabled", False)),
        card_recognition_enabled=bool(models.get("card_recognition_enabled", False)),
        card_detector_backend=str(models.get("card_detector_backend", "heuristic")),
        yolo_card_detector=dict(models.get("yolo_card_detector", {})),
        debug_sample_every=int(debug.get("sample_every_frames", 30)),
        card_hold_frames=int(temporal.get("card_hold_frames", 3)),
        card_confirm_frames=int(temporal.get("card_confirm_frames", 2)),
        card_min_confidence=float(temporal.get("card_min_confidence", 0.45)),
        visual_stable_frames=int(temporal.get("visual_stable_frames", 4)),
        empty_reset_frames=int(temporal.get("empty_reset_frames", 5)),
        clock_ocr_interval_frames=int(models.get("clock_ocr_interval_frames", 5)),
        timer_visibility_threshold=float(temporal.get("timer_visibility_threshold", 0.55)),
        timer_hidden_confirm_frames=int(temporal.get("timer_hidden_confirm_frames", 2)),
        timer_visible_confirm_frames=int(temporal.get("timer_visible_confirm_frames", 2)),
        round_reset_delay_ms=int(temporal.get("round_reset_delay_ms", 1500)),
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        import json

        return json.loads(text)

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read YAML live config files.") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Live config must be a mapping: {path}")
    return data
