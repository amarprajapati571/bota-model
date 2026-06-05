from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class EventSequencer:
    value: int = 0

    def next(self) -> int:
        self.value += 1
        return self.value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def make_event(
    event_type: str,
    table_id: str,
    stream_id: str,
    sequence_number: int,
    payload: dict[str, Any],
    *,
    round_id: str | None = None,
    frame_id: str | None = None,
    video_pts_ms: int | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "event_id": f"evt_{uuid4().hex}",
        "event_type": event_type,
        "schema_version": "1.0",
        "table_id": table_id,
        "stream_id": stream_id,
        "round_id": round_id,
        "frame_id": frame_id,
        "sequence_number": sequence_number,
        "video_pts_ms": video_pts_ms,
        "wall_time_ms": epoch_ms(now),
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "payload": payload,
    }


def stream_health_event(
    table_id: str,
    stream_id: str,
    sequence_number: int,
    *,
    status: str,
    source_connected: bool,
    last_frame_age_ms: int,
    capture_fps: float,
) -> dict[str, Any]:
    return make_event(
        "stream.health",
        table_id,
        stream_id,
        sequence_number,
        {
            "status": status,
            "source_connected": source_connected,
            "frontend_playback_available": True,
            "fps_in": capture_fps,
            "fps_processed": capture_fps,
            "video_latency_ms": 0,
            "ml_latency_ms": 0,
            "queue_lag_ms": 0,
            "last_frame_age_ms": last_frame_age_ms,
        },
    )


def review_required_event(
    table_id: str,
    stream_id: str,
    sequence_number: int,
    *,
    message: str,
    reason_code: str = "ML_MODELS_NOT_CONFIGURED",
) -> dict[str, Any]:
    return make_event(
        "review.required",
        table_id,
        stream_id,
        sequence_number,
        {
            "reason_code": reason_code,
            "message": message,
            "affected_items": [],
            "review_url": "",
        },
    )
