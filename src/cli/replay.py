from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.api.schemas import (
    CardObservation,
    ClockStatus,
    FrameObservation,
    FrameQuality,
    Side,
    Visibility,
    parse_datetime,
)
from src.engine.clock import parse_clock_text
from src.engine.round_state_machine import RoundStateMachine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay JSONL frame observations through the engine.")
    parser.add_argument("--input", required=True, help="Path to JSON Lines frame observations.")
    args = parser.parse_args(argv)

    engine = RoundStateMachine()
    for frame in _read_frames(Path(args.input)):
        for event in engine.update(frame):
            print(json.dumps(event.to_dict(), sort_keys=True))
    return 0


def _read_frames(path: Path) -> list[FrameObservation]:
    frames: list[FrameObservation] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            try:
                frames.append(frame_from_dict(payload))
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError(f"Invalid frame on line {line_number}: {exc}") from exc
    return frames


def frame_from_dict(payload: dict[str, Any]) -> FrameObservation:
    clock_payload = payload.get("clock", {})
    clock = parse_clock_text(clock_payload.get("text_raw"), clock_payload.get("confidence", 1.0))
    if clock_payload.get("status") and clock_payload.get("status") != ClockStatus.VALID.value:
        clock = parse_clock_text(None, clock_payload.get("confidence", 0.0))

    quality_payload = payload.get("frame_quality", {})
    cards = tuple(_card_from_dict(item) for item in payload.get("cards", []))
    return FrameObservation(
        table_id=payload["table_id"],
        camera_id=payload["camera_id"],
        frame_id=payload["frame_id"],
        server_ts_utc=parse_datetime(payload["server_ts_utc"]),
        stream_pts_ms=payload.get("stream_pts_ms"),
        clock=clock,
        cards=cards,
        frame_quality=FrameQuality(
            blur_score=quality_payload.get("blur_score"),
            is_frozen=quality_payload.get("is_frozen", False),
            is_black_frame=quality_payload.get("is_black_frame", False),
            quality_status=quality_payload.get("quality_status", "good"),
        ),
        model_versions=payload.get("model_versions", {}),
    )


def _card_from_dict(payload: dict[str, Any]) -> CardObservation:
    bbox = payload.get("bbox_xyxy")
    return CardObservation(
        side=Side(payload["side"]),
        slot=payload["slot"],
        rank=payload.get("rank"),
        suit=payload.get("suit"),
        confidence=payload.get("confidence", 0.0),
        visibility=Visibility(payload.get("visibility", "visible")),
        bbox_xyxy=tuple(bbox) if bbox else None,
    )


if __name__ == "__main__":
    sys.exit(main())
