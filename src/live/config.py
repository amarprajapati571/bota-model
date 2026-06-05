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


def load_live_config(path: str | Path) -> LiveConfig:
    payload = _load_mapping(Path(path))
    table = payload.get("table", {})
    source = payload.get("source", {})
    viewport = source.get("viewport", {})
    capture = payload.get("capture", {})
    frontend = payload.get("frontend", {})
    overlay = payload.get("overlay_config", {})
    models = payload.get("models", {})

    return LiveConfig(
        table_id=str(table.get("table_id", "MD3212")),
        stream_id=str(table.get("stream_id", "stream_MD3212_live")),
        camera_id=str(table.get("camera_id", "cam-01")),
        source_type=str(source.get("type", "browser_page")),
        source_url=str(source.get("url", "")),
        viewport_width=int(viewport.get("width", 1466)),
        viewport_height=int(viewport.get("height", 746)),
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
