from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from src.api.schemas import CardObservation, FrameObservation, FrameQuality, Side, Visibility
from src.engine.round_state_machine import RoundStateMachine
from src.live.card_detection import detect_card_boxes
from src.live.clock_detection import ClockDetection, detect_clock, missing_clock_detection
from src.live.config import LiveConfig
from src.live.events import EventSequencer, review_required_event
from src.live.roi_calibration import roi_debug_payload, save_debug_overlay
from src.live.round_events import (
    cards_detected_event,
    clock_tick_event,
    frontend_event_from_round_event,
    round_state_event,
)
from src.live.timer_visibility import TimerVisibility, detect_timer_visibility
from src.live.yolo_card_detector import YoloCardDetector, build_yolo_detector


@dataclass(frozen=True)
class LivePipelineResult:
    events: list[dict[str, Any]]
    card_payload: dict[str, list[dict[str, Any]]]
    clock: ClockDetection
    timer: TimerVisibility
    round_state: str
    debug_payload: dict[str, Any]
    processing_ms: float


@dataclass
class StableCardState:
    payload: dict[str, Any]
    seen_count: int = 0
    missed_count: int = 0


@dataclass
class VisualRoundTracker:
    state: str = "WAITING_FOR_STREAM"
    active_round_id: str | None = None
    visible_frames: int = 0
    empty_frames: int = 0
    stable_frames: int = 0
    last_signature: str = ""
    visual_stable_frames: int = 4
    empty_reset_frames: int = 5
    timer_visible_frames: int = 0
    timer_hidden_frames: int = 0
    timer_was_visible: bool = False
    timer_hidden_confirm_frames: int = 2
    timer_visible_confirm_frames: int = 2

    def update(
        self,
        table_id: str,
        timestamp: datetime,
        card_payload: dict[str, list[dict]],
        timer: TimerVisibility,
    ) -> tuple[str, str]:
        visible_count = len(card_payload["player_cards"]) + len(card_payload["banker_cards"])
        signature = _card_signature(card_payload)
        timer_became_visible = False

        if visible_count:
            self.visible_frames += 1
            self.empty_frames = 0
        else:
            self.empty_frames += 1
            self.visible_frames = 0

        if signature and signature == self.last_signature:
            self.stable_frames += 1
        else:
            self.stable_frames = 1 if signature else 0
        self.last_signature = signature

        if timer.visible:
            self.timer_visible_frames += 1
            self.timer_hidden_frames = 0
            if not self.timer_was_visible and self.timer_visible_frames >= self.timer_visible_confirm_frames:
                timer_became_visible = True
            if self.timer_visible_frames >= self.timer_visible_confirm_frames:
                self.timer_was_visible = True
        else:
            self.timer_hidden_frames += 1
            self.timer_visible_frames = 0

        previous = self.state
        if self.state == "WAITING_FOR_STREAM" and timer.visible:
            self.state = "WAITING_FOR_BETS"
        elif self.state in {"WAITING_FOR_STREAM", "WAITING_FOR_BETS", "RESET_WAITING_NEXT_BETS"} and timer.visible:
            self.state = "BETTING_COUNTDOWN_VISIBLE"
        elif (
            self.state in {"WAITING_FOR_BETS", "BETTING_COUNTDOWN_VISIBLE"}
            and self.timer_was_visible
            and self.timer_hidden_frames >= self.timer_hidden_confirm_frames
        ):
            self.active_round_id = f"{table_id}-{timestamp.strftime('%Y%m%d-%H%M%S')}"
            self.state = "MATCH_STARTED_TIMER_HIDDEN"
        elif self.state == "MATCH_STARTED_TIMER_HIDDEN" and visible_count:
            self.state = "DEALING"
        elif self.state == "DEALING" and _minimum_cards_visible(card_payload):
            self.state = "CARDS_DETECTED"
        elif self.state == "CARDS_DETECTED" and self.stable_frames >= self.visual_stable_frames:
            self.state = "ROUND_COMPLETE"
        elif self.state in {"ROUND_COMPLETE", "MATCH_STARTED_TIMER_HIDDEN", "DEALING", "CARDS_DETECTED"} and (
            timer_became_visible or (timer.visible and self.timer_visible_frames >= self.timer_visible_confirm_frames)
        ):
            self.state = "RESET_WAITING_NEXT_BETS"
            self.active_round_id = None
        elif self.state == "RESET_WAITING_NEXT_BETS" and timer.visible:
            self.state = "BETTING_COUNTDOWN_VISIBLE"

        reason = "unchanged" if previous == self.state else f"{previous}->{self.state}"
        return self.state, reason

    def card_capture_enabled(self) -> bool:
        return self.state in {
            "MATCH_STARTED_TIMER_HIDDEN",
            "DEALING",
            "CARDS_DETECTED",
            "ROUND_RESULT_READY",
            "ROUND_COMPLETE",
        }


@dataclass
class LiveInferencePipeline:
    config: LiveConfig
    sequencer: EventSequencer
    engine: RoundStateMachine = field(default_factory=RoundStateMachine)
    card_hold_frames: int = 3
    card_confirm_frames: int = 2
    debug_sample_every: int = 30
    card_min_confidence: float = 0.45
    clock_ocr_interval_frames: int = 5
    _stable_cards: dict[str, StableCardState] = field(default_factory=dict)
    _visual_tracker: VisualRoundTracker = field(default_factory=VisualRoundTracker)
    _last_clock: ClockDetection | None = None
    _reviewed_round_ids: set[str] = field(default_factory=set)
    _card_detector: YoloCardDetector | None = field(default=None, init=False)
    _card_detector_status: str = "heuristic"

    def __post_init__(self) -> None:
        self.card_hold_frames = self.config.card_hold_frames
        self.card_confirm_frames = self.config.card_confirm_frames
        self.debug_sample_every = self.config.debug_sample_every
        self.card_min_confidence = self.config.card_min_confidence
        self.clock_ocr_interval_frames = max(1, self.config.clock_ocr_interval_frames)
        self._visual_tracker.visual_stable_frames = self.config.visual_stable_frames
        self._visual_tracker.empty_reset_frames = self.config.empty_reset_frames
        self._visual_tracker.timer_hidden_confirm_frames = self.config.timer_hidden_confirm_frames
        self._visual_tracker.timer_visible_confirm_frames = self.config.timer_visible_confirm_frames
        if self.config.card_detector_backend.lower() == "yolo":
            try:
                self._card_detector = build_yolo_detector(self.config.yolo_card_detector)
            except Exception as exc:  # noqa: BLE001 - fallback is intentional for live resilience.
                self._card_detector = None
                self._card_detector_status = f"yolo_unavailable:{exc}"
            else:
                self._card_detector_status = "yolo"

    def process_frame(
        self,
        image_bytes: bytes,
        captured_at: datetime,
        frame_id: str,
        frame_count: int,
    ) -> LivePipelineResult:
        started = perf_counter()
        timer = detect_timer_visibility(
            image_bytes,
            self.config.rois,
            visibility_threshold=self.config.timer_visibility_threshold,
        )
        raw_card_payload = self._filter_card_payload(self._detect_cards(image_bytes))
        capture_enabled = self._visual_tracker.card_capture_enabled()
        card_payload = raw_card_payload if capture_enabled else _empty_card_payload()
        if not capture_enabled and timer.visible:
            self._stable_cards.clear()
        stable_payload = self._stabilize_cards(card_payload)
        clock = self._detect_clock_throttled(image_bytes, frame_count)
        visual_state, visual_reason = self._visual_tracker.update(
            self.config.table_id, captured_at, stable_payload, timer
        )
        if not self._visual_tracker.card_capture_enabled():
            self._stable_cards.clear()
            stable_payload = _empty_card_payload()
        classified_cards = _classified_observations(stable_payload)

        frame = FrameObservation(
            table_id=self.config.table_id,
            camera_id=self.config.camera_id,
            frame_id=frame_id,
            server_ts_utc=captured_at,
            stream_pts_ms=None,
            clock=clock.observation,
            cards=classified_cards,
            frame_quality=FrameQuality(),
            model_versions={
                "live_pipeline": "heuristic-v2",
                "card_detector": self._card_detector_status,
                "clock_detector": clock.source,
            },
        )

        events = [
            clock_tick_event(
                self.config.table_id,
                self.config.stream_id,
                self.sequencer.next(),
                clock.to_event_payload(),
                frame_id=frame_id,
            ),
            round_state_event(
                self.config.table_id,
                self.config.stream_id,
                self.sequencer.next(),
                round_id=self._visual_tracker.active_round_id,
                state=visual_state,
                confidence=_state_confidence(stable_payload, clock, timer),
                reason=visual_reason,
                timer_visibility=timer.to_event_payload(),
            ),
        ]

        if self._visual_tracker.card_capture_enabled() and (
            stable_payload["player_cards"] or stable_payload["banker_cards"]
        ):
            events.append(
                cards_detected_event(
                    self.config.table_id,
                    self.config.stream_id,
                    self.sequencer.next(),
                    {
                        "player_cards": stable_payload["player_cards"],
                        "banker_cards": stable_payload["banker_cards"],
                        "overall_confidence": _mean_detection_confidence(stable_payload),
                        "identity_status": "boxes_only",
                    },
                    frame_id=frame_id,
                    round_id=self._visual_tracker.active_round_id,
                )
            )

        for round_event in self.engine.update(frame):
            events.append(
                frontend_event_from_round_event(
                    round_event,
                    self.config.table_id,
                    self.config.stream_id,
                    self.sequencer.next(),
                )
            )

        active_round_id = self._visual_tracker.active_round_id or frame_id
        if (
            visual_state == "ROUND_COMPLETE"
            and not classified_cards
            and active_round_id not in self._reviewed_round_ids
        ):
            self._reviewed_round_ids.add(active_round_id)
            events.append(
                review_required_event(
                    self.config.table_id,
                    self.config.stream_id,
                    self.sequencer.next(),
                    message=(
                        "Cards are visually stable, but rank/suit classification is not configured. "
                        "Winner cannot be confirmed."
                    ),
                    reason_code="CARD_IDENTITY_NOT_CONFIGURED",
                )
            )

        processing_ms = round((perf_counter() - started) * 1000, 3)
        debug_payload = self._debug_payload(
            frame_id,
            captured_at,
            image_bytes,
            raw_card_payload,
            stable_payload,
            clock,
            timer,
            visual_state,
            processing_ms,
        )
        self._save_debug_artifacts(
            image_bytes, frame_id, frame_count, stable_payload, clock, debug_payload
        )
        return LivePipelineResult(
            events, stable_payload, clock, timer, visual_state, debug_payload, processing_ms
        )

    def _detect_cards(self, image_bytes: bytes) -> dict[str, list[dict[str, Any]]]:
        if self._card_detector is not None:
            return self._card_detector.detect(image_bytes, self.config.rois)
        return detect_card_boxes(image_bytes, self.config.rois)

    def _detect_clock_throttled(self, image_bytes: bytes, frame_count: int) -> ClockDetection:
        if not self.config.clock_ocr_enabled:
            if self._last_clock:
                return self._last_clock
            self._last_clock = missing_clock_detection("disabled")
            return self._last_clock
        if self._last_clock and frame_count % self.clock_ocr_interval_frames != 0:
            return self._last_clock
        self._last_clock = detect_clock(image_bytes, self.config.rois)
        return self._last_clock

    def _filter_card_payload(
        self, card_payload: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            side_key: [
                card
                for card in cards
                if _card_confidence(card) >= self.card_min_confidence and _valid_bbox(card)
            ]
            for side_key, cards in card_payload.items()
        }

    def _stabilize_cards(
        self, card_payload: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        current: dict[str, dict[str, Any]] = {}
        for side_key in ("player_cards", "banker_cards"):
            side = "PLAYER" if side_key == "player_cards" else "BANKER"
            for card in card_payload.get(side_key, []):
                slot = int(card.get("slot", 0))
                key = f"{side}:{slot}"
                current[key] = {**card, "side": side}

        for key, payload in current.items():
            existing = self._stable_cards.get(key)
            if existing:
                seen_count = existing.seen_count + 1
                best = payload if _card_confidence(payload) >= _card_confidence(existing.payload) else existing.payload
                self._stable_cards[key] = StableCardState(best, seen_count, 0)
            else:
                self._stable_cards[key] = StableCardState(payload, 1, 0)

        for key, existing in list(self._stable_cards.items()):
            if key in current:
                continue
            missed_count = existing.missed_count + 1
            if missed_count > self.card_hold_frames:
                del self._stable_cards[key]
            else:
                self._stable_cards[key] = StableCardState(
                    existing.payload, existing.seen_count, missed_count
                )

        result = {"player_cards": [], "banker_cards": []}
        for key, stable in sorted(self._stable_cards.items()):
            if stable.seen_count < self.card_confirm_frames:
                continue
            card = {
                **stable.payload,
                "stable": stable.missed_count == 0 and stable.seen_count >= self.card_confirm_frames,
                "seen_frames": stable.seen_count,
                "missed_frames": stable.missed_count,
            }
            target = "player_cards" if key.startswith("PLAYER:") else "banker_cards"
            result[target].append(card)
        return result

    def _debug_payload(
        self,
        frame_id: str,
        captured_at: datetime,
        image_bytes: bytes,
        raw_cards: dict[str, list[dict[str, Any]]],
        stable_cards: dict[str, list[dict[str, Any]]],
        clock: ClockDetection,
        timer: TimerVisibility,
        visual_state: str,
        processing_ms: float,
    ) -> dict[str, Any]:
        try:
            from PIL import Image
        except ImportError:
            width = height = 0
        else:
            from io import BytesIO

            image = Image.open(BytesIO(image_bytes))
            width, height = image.size
        return {
            "frame_id": frame_id,
            "captured_at": captured_at.isoformat().replace("+00:00", "Z"),
            "source": _redacted_source(self.config.source_url),
            "image": {"width": width, "height": height},
            "rois": roi_debug_payload(self.config.rois, width, height) if width and height else {},
            "clock": clock.to_event_payload(),
            "timer_visibility": timer.to_event_payload(),
            "raw_cards": raw_cards,
            "stable_cards": stable_cards,
            "card_capture_enabled": self._visual_tracker.card_capture_enabled(),
            "ignored_raw_card_count": _card_count(raw_cards)
            if not self._visual_tracker.card_capture_enabled()
            else 0,
            "round_state": visual_state,
            "identity_status": "boxes_only",
            "card_detector": self._card_detector_status,
            "processing_ms": processing_ms,
            "thresholds": {
                "card_min_confidence": self.card_min_confidence,
                "card_confirm_frames": self.card_confirm_frames,
                "card_hold_frames": self.card_hold_frames,
                "visual_stable_frames": self._visual_tracker.visual_stable_frames,
                "empty_reset_frames": self._visual_tracker.empty_reset_frames,
                "clock_ocr_interval_frames": self.clock_ocr_interval_frames,
                "timer_visibility_threshold": self.config.timer_visibility_threshold,
                "timer_hidden_confirm_frames": self.config.timer_hidden_confirm_frames,
                "timer_visible_confirm_frames": self.config.timer_visible_confirm_frames,
            },
        }

    def _save_debug_artifacts(
        self,
        image_bytes: bytes,
        frame_id: str,
        frame_count: int,
        card_payload: dict[str, list[dict[str, Any]]],
        clock: ClockDetection,
        debug_payload: dict[str, Any],
    ) -> None:
        if self.debug_sample_every <= 0:
            return
        if frame_count % self.debug_sample_every != 0 and frame_count != 1:
            return

        debug_dir = self.config.evidence_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_frame_id = frame_id.replace("/", "_")
        (debug_dir / f"{safe_frame_id}.json").write_text(
            json.dumps(debug_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        save_debug_overlay(
            image_bytes,
            debug_dir / f"{safe_frame_id}.jpg",
            self.config.rois,
            card_payload,
            {
                "clock_text": (
                    f"timer visible={debug_payload.get('timer_visibility', {}).get('visible')} "
                    f"conf={debug_payload.get('timer_visibility', {}).get('confidence')}"
                ),
                "confidence": debug_payload.get("timer_visibility", {}).get("confidence", 0.0),
            },
        )


def _classified_observations(
    card_payload: dict[str, list[dict[str, Any]]]
) -> tuple[CardObservation, ...]:
    observations: list[CardObservation] = []
    for side_key, side in (("player_cards", Side.PLAYER), ("banker_cards", Side.BANKER)):
        for card in card_payload.get(side_key, []):
            rank = card.get("rank")
            suit = card.get("suit")
            if not rank or not suit:
                continue
            bbox = card.get("bbox_norm")
            observations.append(
                CardObservation(
                    side=side,
                    slot=f"{side.value[0]}{card.get('slot')}",
                    rank=rank,
                    suit=suit,
                    confidence=min(
                        float(card.get("det_confidence", 0.0)),
                        float(card.get("rank_confidence", 0.0)),
                        float(card.get("suit_confidence", 0.0)),
                    ),
                    visibility=Visibility.VISIBLE,
                    bbox_xyxy=(
                        float(bbox["x1"]),
                        float(bbox["y1"]),
                        float(bbox["x2"]),
                        float(bbox["y2"]),
                    )
                    if bbox
                    else None,
                )
            )
    return tuple(observations)


def _empty_card_payload() -> dict[str, list[dict[str, Any]]]:
    return {"player_cards": [], "banker_cards": []}


def _card_count(card_payload: dict[str, list[dict]]) -> int:
    return len(card_payload.get("player_cards", [])) + len(card_payload.get("banker_cards", []))


def _mean_detection_confidence(card_payload: dict[str, list[dict]]) -> float:
    confidences = [
        _card_confidence(card)
        for card in card_payload["player_cards"] + card_payload["banker_cards"]
        if card.get("det_confidence") is not None
    ]
    if not confidences:
        return 0.0
    return round(sum(confidences) / len(confidences), 4)


def _card_confidence(card: dict[str, Any]) -> float:
    return float(card.get("det_confidence") or card.get("confidence") or 0.0)


def _valid_bbox(card: dict[str, Any]) -> bool:
    bbox = card.get("bbox_norm")
    if not bbox:
        return False
    try:
        x1 = float(bbox["x1"])
        y1 = float(bbox["y1"])
        x2 = float(bbox["x2"])
        y2 = float(bbox["y2"])
    except (KeyError, TypeError, ValueError):
        return False
    return 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1


def _minimum_cards_visible(card_payload: dict[str, list[dict]]) -> bool:
    return len(card_payload["player_cards"]) >= 2 and len(card_payload["banker_cards"]) >= 2


def _card_signature(card_payload: dict[str, list[dict]]) -> str:
    parts: list[str] = []
    for side_key in ("player_cards", "banker_cards"):
        for card in card_payload.get(side_key, []):
            if int(card.get("missed_frames", 0)) > 0:
                continue
            bbox = card.get("bbox_norm") or {}
            parts.append(
                f"{side_key}:{card.get('slot')}:{round(float(bbox.get('x1', 0)), 3)}:"
                f"{round(float(bbox.get('y1', 0)), 3)}"
            )
    return "|".join(sorted(parts))


def _state_confidence(
    card_payload: dict[str, list[dict]], clock: ClockDetection, timer: TimerVisibility
) -> float:
    card_confidence = _mean_detection_confidence(card_payload)
    timer_confidence = timer.confidence
    clock_confidence = clock.observation.confidence
    return round(max(card_confidence, timer_confidence, clock_confidence), 4)


def _redacted_source(source_url: str) -> dict[str, str]:
    parsed = urlparse(source_url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "path": parsed.path,
    }
