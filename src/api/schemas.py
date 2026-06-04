from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Side(str, Enum):
    PLAYER = "PLAYER"
    BANKER = "BANKER"


class Visibility(str, Enum):
    EMPTY = "empty"
    VISIBLE = "visible"
    PARTIAL = "partial"
    OCCLUDED = "occluded"
    UNKNOWN = "unknown"


class Winner(str, Enum):
    PLAYER = "PLAYER"
    BANKER = "BANKER"
    TIE = "TIE"


class ClockStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"


@dataclass(frozen=True)
class ClockObservation:
    text_raw: str | None
    parsed_time: str | None
    seconds_of_day: int | None
    confidence: float
    status: ClockStatus = ClockStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_raw": self.text_raw,
            "parsed_time": self.parsed_time,
            "seconds_of_day": self.seconds_of_day,
            "confidence": self.confidence,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class FrameQuality:
    blur_score: float | None = None
    is_frozen: bool = False
    is_black_frame: bool = False
    quality_status: str = "good"

    @property
    def is_usable(self) -> bool:
        return self.quality_status == "good" and not self.is_frozen and not self.is_black_frame

    def to_dict(self) -> dict[str, Any]:
        return {
            "blur_score": self.blur_score,
            "is_frozen": self.is_frozen,
            "is_black_frame": self.is_black_frame,
            "quality_status": self.quality_status,
        }


@dataclass(frozen=True)
class CardObservation:
    side: Side
    slot: str
    rank: str | None
    suit: str | None
    confidence: float
    visibility: Visibility = Visibility.VISIBLE
    bbox_xyxy: tuple[float, float, float, float] | None = None

    @property
    def card_id(self) -> str | None:
        if not self.rank or not self.suit:
            return None
        return f"{self.rank.upper()}-{self.suit.lower()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side.value,
            "slot": self.slot,
            "rank": self.rank,
            "suit": self.suit,
            "bbox_xyxy": list(self.bbox_xyxy) if self.bbox_xyxy else None,
            "confidence": self.confidence,
            "visibility": self.visibility.value,
        }


@dataclass(frozen=True)
class FrameObservation:
    table_id: str
    camera_id: str
    frame_id: str
    server_ts_utc: datetime
    stream_pts_ms: int | None
    clock: ClockObservation
    cards: tuple[CardObservation, ...]
    frame_quality: FrameQuality = field(default_factory=FrameQuality)
    model_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": "frame.observation",
            "schema_version": "1.0",
            "table_id": self.table_id,
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "server_ts_utc": isoformat_utc(self.server_ts_utc),
            "stream_pts_ms": self.stream_pts_ms,
            "clock": self.clock.to_dict(),
            "cards": [card.to_dict() for card in self.cards],
            "frame_quality": self.frame_quality.to_dict(),
            "model_versions": self.model_versions,
        }


@dataclass(frozen=True)
class ValidationResult:
    baccarat_rules_valid: bool
    card_count_valid: bool
    clock_boundary_valid: bool
    needs_review: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "baccarat_rules_valid": self.baccarat_rules_valid,
            "card_count_valid": self.card_count_valid,
            "clock_boundary_valid": self.clock_boundary_valid,
            "needs_review": self.needs_review,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RoundEvent:
    event_type: str
    round_id: str
    table_id: str
    camera_id: str
    started_at_utc: datetime
    ended_at_utc: datetime | None
    started_at_clock: str | None
    ended_at_clock: str | None
    boundary_source: str
    player_cards: tuple[CardObservation, ...]
    banker_cards: tuple[CardObservation, ...]
    player_total: int | None
    banker_total: int | None
    winner: Winner | None
    round_confidence: float
    validation: ValidationResult
    evidence: dict[str, Any] = field(default_factory=dict)
    model_versions: dict[str, str] = field(default_factory=dict)
    round_index_source: str = "clock_minute"
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "round_id": self.round_id,
            "table_id": self.table_id,
            "camera_id": self.camera_id,
            "round_index_source": self.round_index_source,
            "started_at_utc": isoformat_utc(self.started_at_utc),
            "ended_at_utc": isoformat_utc(self.ended_at_utc) if self.ended_at_utc else None,
            "started_at_clock": self.started_at_clock,
            "ended_at_clock": self.ended_at_clock,
            "boundary_source": self.boundary_source,
            "player_cards": [card.to_dict() for card in self.player_cards],
            "banker_cards": [card.to_dict() for card in self.banker_cards],
            "player_total": self.player_total,
            "banker_total": self.banker_total,
            "winner": self.winner.value if self.winner else None,
            "round_confidence": self.round_confidence,
            "validation": self.validation.to_dict(),
            "evidence": self.evidence,
            "model_versions": self.model_versions,
        }


def isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
