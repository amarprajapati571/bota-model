from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from src.api.schemas import CardObservation, FrameObservation, FrameQuality, Side
from src.engine.clock import parse_clock_text
from src.engine.round_state_machine import RoundEngineConfig, RoundStateMachine
from src.engine.temporal_tracker import TemporalCardTracker, TemporalVotingConfig


def frame(
    second: int,
    cards: tuple[CardObservation, ...] = (),
    frame_id: str | None = None,
) -> FrameObservation:
    timestamp = datetime(2026, 1, 1, 18, 43, tzinfo=timezone.utc) + timedelta(seconds=second)
    return FrameObservation(
        table_id="MD3212",
        camera_id="cam-01",
        frame_id=frame_id or f"frame-{second}",
        server_ts_utc=timestamp,
        stream_pts_ms=second * 1000,
        clock=parse_clock_text(timestamp.strftime("%H:%M:%S"), 0.98),
        cards=cards,
        frame_quality=FrameQuality(),
        model_versions={"round_engine": "test"},
    )


def visible_cards() -> tuple[CardObservation, ...]:
    return (
        CardObservation(Side.PLAYER, "P1", "6", "hearts", 0.97),
        CardObservation(Side.PLAYER, "P2", "K", "spades", 0.95),
        CardObservation(Side.BANKER, "B1", "6", "hearts", 0.94),
        CardObservation(Side.BANKER, "B2", "Q", "diamonds", 0.96),
    )


class RoundStateMachineTests(unittest.TestCase):
    def test_opens_and_closes_round_from_stable_cards(self) -> None:
        engine = RoundStateMachine(
            config=RoundEngineConfig(min_clock_confirm_frames=3, result_stable_seconds=1.0),
            tracker=TemporalCardTracker(
                TemporalVotingConfig(card_window_frames=5, min_valid_votes=2, card_lock_confidence=0.9)
            ),
        )
        emitted = []
        for second in (0, 1, 2):
            emitted.extend(engine.update(frame(second)))

        self.assertEqual([event.event_type for event in emitted], ["round.started"])

        for second in (5, 6, 7, 8):
            emitted.extend(engine.update(frame(second, visible_cards())))

        closed = [event for event in emitted if event.event_type == "round.closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].winner.value, "TIE")
        self.assertFalse(closed[0].validation.needs_review)


if __name__ == "__main__":
    unittest.main()
