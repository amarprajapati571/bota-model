from __future__ import annotations

import unittest

from src.api.schemas import CardObservation, Side
from src.engine.temporal_tracker import TemporalCardTracker, TemporalVotingConfig


class TemporalTrackerTests(unittest.TestCase):
    def test_locks_after_enough_consistent_votes(self) -> None:
        tracker = TemporalCardTracker(
            TemporalVotingConfig(card_window_frames=5, min_valid_votes=3, card_lock_confidence=0.9)
        )
        observation = CardObservation(Side.PLAYER, "P1", "5", "hearts", 0.95)
        for _ in range(3):
            tracker.update((observation,))

        locked = tracker.locked_cards()
        self.assertEqual(len(locked), 1)
        self.assertEqual(locked[0].card_id, "5-hearts")

    def test_unlocks_after_contradictions(self) -> None:
        tracker = TemporalCardTracker(
            TemporalVotingConfig(
                card_window_frames=6,
                min_valid_votes=2,
                card_lock_confidence=0.9,
                unlock_on_contradiction_frames=2,
            )
        )
        first = CardObservation(Side.PLAYER, "P1", "5", "hearts", 0.95)
        second = CardObservation(Side.PLAYER, "P1", "6", "hearts", 0.95)
        tracker.update((first,))
        tracker.update((first,))
        self.assertEqual(len(tracker.locked_cards()), 1)
        tracker.update((second,))
        tracker.update((second,))
        self.assertEqual(tracker.locked_cards(), ())


if __name__ == "__main__":
    unittest.main()
