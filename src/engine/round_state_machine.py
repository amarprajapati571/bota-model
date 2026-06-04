from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.api.schemas import (
    CardObservation,
    ClockStatus,
    FrameObservation,
    RoundEvent,
    Side,
    ValidationResult,
)
from src.engine.baccarat_rules import score_hands, validate_round_cards
from src.engine.clock import ClockSmoother
from src.engine.confidence import score_round_confidence
from src.engine.temporal_tracker import TemporalCardTracker, TemporalVotingConfig


class RoundState(str, Enum):
    WAIT_STREAM = "WAIT_STREAM"
    CALIBRATING = "CALIBRATING"
    WAIT_ROUND = "WAIT_ROUND"
    ROUND_OPEN = "ROUND_OPEN"
    DEALING = "DEALING"
    CARDS_VISIBLE = "CARDS_VISIBLE"
    RESULT_LOCKED = "RESULT_LOCKED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class RoundEngineConfig:
    expected_round_seconds: int = 60
    start_second_window: tuple[int, int] = (0, 5)
    end_second_window: tuple[int, int] = (50, 59)
    min_clock_confirm_frames: int = 3
    result_stable_seconds: float = 1.5
    round_timeout_seconds: float = 90.0
    allow_visual_start_without_clock: bool = True
    auto_publish_confidence: float = 0.90
    review_confidence_threshold: float = 0.80


@dataclass
class ActiveRound:
    round_id: str
    table_id: str
    camera_id: str
    started_at_utc: datetime
    started_at_clock: str | None
    boundary_source: str
    best_frame_id: str | None = None
    result_locked_at: datetime | None = None


@dataclass
class RoundStateMachine:
    config: RoundEngineConfig = field(default_factory=RoundEngineConfig)
    tracker: TemporalCardTracker = field(
        default_factory=lambda: TemporalCardTracker(TemporalVotingConfig())
    )
    clock_smoother: ClockSmoother = field(default_factory=ClockSmoother)
    state: RoundState = RoundState.WAIT_STREAM
    active_round: ActiveRound | None = None
    _last_closed_round_id: str | None = None
    _last_cards_present: bool = False

    def update(self, frame: FrameObservation) -> list[RoundEvent]:
        events: list[RoundEvent] = []
        clock = self.clock_smoother.update(frame.clock, frame.server_ts_utc)

        if self.state == RoundState.WAIT_STREAM and frame.frame_quality.is_usable:
            self.state = RoundState.CALIBRATING
        if self.state == RoundState.CALIBRATING:
            self.state = RoundState.WAIT_ROUND

        cards_present = bool(frame.cards)
        if self.state == RoundState.WAIT_ROUND and self._should_open_round(frame):
            events.append(self._open_round(frame, "clock_and_visual"))
        elif (
            self.state == RoundState.WAIT_ROUND
            and self.config.allow_visual_start_without_clock
            and cards_present
            and not self._last_cards_present
        ):
            events.append(self._open_round(frame, "visual_fallback"))

        if self.active_round:
            self.tracker.update(frame.cards)
            locked_cards = self.tracker.locked_cards()
            if self.state == RoundState.ROUND_OPEN and cards_present:
                self.state = RoundState.DEALING
            if self.state == RoundState.DEALING and self._minimum_cards_visible(locked_cards):
                self.state = RoundState.CARDS_VISIBLE
            if self.state in (RoundState.CARDS_VISIBLE, RoundState.RESULT_LOCKED):
                maybe_closed = self._maybe_lock_or_close(frame, locked_cards)
                events.extend(maybe_closed)
            elif self._round_timed_out(frame.server_ts_utc):
                events.append(self._review_event(frame, "round_timeout"))
                self._reset()

        self._last_cards_present = cards_present
        return events

    def _should_open_round(self, frame: FrameObservation) -> bool:
        if frame.clock.status != ClockStatus.VALID:
            return False
        if frame.cards:
            return False
        return self.clock_smoother.confirmed_start_boundary(
            self.config.start_second_window,
            self.config.min_clock_confirm_frames,
        )

    def _open_round(self, frame: FrameObservation, boundary_source: str) -> RoundEvent:
        round_id = self._round_id(frame)
        if round_id == self._last_closed_round_id:
            return self._review_event(frame, "duplicate_round_id")

        self.tracker.clear()
        self.active_round = ActiveRound(
            round_id=round_id,
            table_id=frame.table_id,
            camera_id=frame.camera_id,
            started_at_utc=frame.server_ts_utc,
            started_at_clock=frame.clock.parsed_time,
            boundary_source=boundary_source,
            best_frame_id=frame.frame_id,
        )
        self.state = RoundState.ROUND_OPEN
        validation = ValidationResult(False, False, frame.clock.status == ClockStatus.VALID, False, ())
        return RoundEvent(
            event_type="round.started",
            round_id=round_id,
            table_id=frame.table_id,
            camera_id=frame.camera_id,
            started_at_utc=frame.server_ts_utc,
            ended_at_utc=None,
            started_at_clock=frame.clock.parsed_time,
            ended_at_clock=None,
            boundary_source=boundary_source,
            player_cards=(),
            banker_cards=(),
            player_total=None,
            banker_total=None,
            winner=None,
            round_confidence=frame.clock.confidence,
            validation=validation,
            evidence={"best_frame_id": frame.frame_id},
            model_versions=frame.model_versions,
        )

    def _maybe_lock_or_close(
        self, frame: FrameObservation, locked_cards: tuple[CardObservation, ...]
    ) -> list[RoundEvent]:
        player_cards = tuple(card for card in locked_cards if card.side == Side.PLAYER)
        banker_cards = tuple(card for card in locked_cards if card.side == Side.BANKER)
        if not self._minimum_cards_visible(locked_cards):
            return []

        validation = validate_round_cards(
            player_cards,
            banker_cards,
            clock_boundary_valid=self.active_round.boundary_source != "visual_fallback"
            if self.active_round
            else False,
        )
        if validation.card_count_valid:
            if self.active_round and self.active_round.result_locked_at is None:
                self.active_round.result_locked_at = frame.server_ts_utc
                self.state = RoundState.RESULT_LOCKED
                return []

        if self.state == RoundState.RESULT_LOCKED and self._result_stable(frame.server_ts_utc):
            return [self._close_round(frame, player_cards, banker_cards, validation)]
        return []

    def _close_round(
        self,
        frame: FrameObservation,
        player_cards: tuple[CardObservation, ...],
        banker_cards: tuple[CardObservation, ...],
        validation: ValidationResult,
    ) -> RoundEvent:
        assert self.active_round is not None
        outcome = score_hands(player_cards, banker_cards) if validation.card_count_valid else None
        confidence = score_round_confidence(
            frame.clock.confidence,
            player_cards,
            banker_cards,
            validation,
            frame.frame_quality,
        )
        validation = ValidationResult(
            validation.baccarat_rules_valid,
            validation.card_count_valid,
            validation.clock_boundary_valid,
            confidence < self.config.auto_publish_confidence or validation.needs_review,
            validation.warnings,
        )
        event = RoundEvent(
            event_type="round.closed",
            round_id=self.active_round.round_id,
            table_id=frame.table_id,
            camera_id=frame.camera_id,
            started_at_utc=self.active_round.started_at_utc,
            ended_at_utc=frame.server_ts_utc,
            started_at_clock=self.active_round.started_at_clock,
            ended_at_clock=frame.clock.parsed_time,
            boundary_source=self.active_round.boundary_source,
            player_cards=player_cards,
            banker_cards=banker_cards,
            player_total=outcome.player_total if outcome else None,
            banker_total=outcome.banker_total if outcome else None,
            winner=outcome.winner if outcome else None,
            round_confidence=confidence,
            validation=validation,
            evidence={"best_frame_id": frame.frame_id},
            model_versions=frame.model_versions,
        )
        self._last_closed_round_id = self.active_round.round_id
        self._reset()
        return event

    def _review_event(self, frame: FrameObservation, reason: str) -> RoundEvent:
        active = self.active_round
        round_id = active.round_id if active else self._round_id(frame)
        validation = ValidationResult(False, False, False, True, (reason,))
        return RoundEvent(
            event_type="round.review",
            round_id=round_id,
            table_id=frame.table_id,
            camera_id=frame.camera_id,
            started_at_utc=active.started_at_utc if active else frame.server_ts_utc,
            ended_at_utc=frame.server_ts_utc,
            started_at_clock=active.started_at_clock if active else frame.clock.parsed_time,
            ended_at_clock=frame.clock.parsed_time,
            boundary_source=active.boundary_source if active else "unknown",
            player_cards=(),
            banker_cards=(),
            player_total=None,
            banker_total=None,
            winner=None,
            round_confidence=0.0,
            validation=validation,
            evidence={"best_frame_id": frame.frame_id},
            model_versions=frame.model_versions,
        )

    def _minimum_cards_visible(self, cards: tuple[CardObservation, ...]) -> bool:
        player_count = sum(card.side == Side.PLAYER for card in cards)
        banker_count = sum(card.side == Side.BANKER for card in cards)
        return player_count >= 2 and banker_count >= 2

    def _round_timed_out(self, now: datetime) -> bool:
        if not self.active_round:
            return False
        return (now - self.active_round.started_at_utc).total_seconds() > self.config.round_timeout_seconds

    def _result_stable(self, now: datetime) -> bool:
        if not self.active_round or not self.active_round.result_locked_at:
            return False
        return (
            now - self.active_round.result_locked_at
        ).total_seconds() >= self.config.result_stable_seconds

    def _round_id(self, frame: FrameObservation) -> str:
        return f"{frame.table_id}-{frame.server_ts_utc.strftime('%Y%m%d-%H%M')}"

    def _reset(self) -> None:
        self.active_round = None
        self.tracker.clear()
        self.state = RoundState.WAIT_ROUND
