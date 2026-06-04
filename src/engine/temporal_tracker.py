from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from src.api.schemas import CardObservation, Visibility


@dataclass(frozen=True)
class LockedSlot:
    observation: CardObservation
    votes: int
    mean_confidence: float
    contradiction_count: int = 0


@dataclass
class TemporalVotingConfig:
    card_window_frames: int = 15
    min_valid_votes: int = 8
    card_lock_confidence: float = 0.90
    occlusion_confidence_threshold: float = 0.60
    unlock_on_contradiction_frames: int = 6


@dataclass
class TemporalCardTracker:
    config: TemporalVotingConfig = field(default_factory=TemporalVotingConfig)
    _history: dict[str, deque[CardObservation]] = field(default_factory=lambda: defaultdict(deque))
    _locked: dict[str, LockedSlot] = field(default_factory=dict)

    def update(self, observations: tuple[CardObservation, ...]) -> None:
        seen_slots: set[str] = set()
        for observation in observations:
            if not self._is_valid_vote(observation):
                continue
            seen_slots.add(observation.slot)
            locked = self._locked.get(observation.slot)
            if locked and locked.observation.card_id != observation.card_id:
                contradiction_count = locked.contradiction_count + 1
                if contradiction_count >= self.config.unlock_on_contradiction_frames:
                    del self._locked[observation.slot]
                    self._history[observation.slot].clear()
                else:
                    self._locked[observation.slot] = LockedSlot(
                        locked.observation,
                        locked.votes,
                        locked.mean_confidence,
                        contradiction_count,
                    )
                continue
            slot_history = self._history[observation.slot]
            slot_history.append(observation)
            while len(slot_history) > self.config.card_window_frames:
                slot_history.popleft()
            self._recompute_lock(observation.slot)

        for slot, locked in list(self._locked.items()):
            if slot in seen_slots:
                continue
            self._locked[slot] = LockedSlot(
                locked.observation,
                locked.votes,
                locked.mean_confidence,
                locked.contradiction_count,
            )

    def locked_cards(self) -> tuple[CardObservation, ...]:
        return tuple(
            locked.observation for _, locked in sorted(self._locked.items(), key=lambda item: item[0])
        )

    def clear(self) -> None:
        self._history.clear()
        self._locked.clear()

    def contradiction_slots(self) -> tuple[str, ...]:
        return tuple(
            slot
            for slot, locked in sorted(self._locked.items())
            if locked.contradiction_count >= self.config.unlock_on_contradiction_frames
        )

    @staticmethod
    def _is_valid_vote(observation: CardObservation) -> bool:
        return (
            observation.card_id is not None
            and observation.visibility == Visibility.VISIBLE
            and observation.confidence > 0
        )

    def _recompute_lock(self, slot: str) -> None:
        history = list(self._history[slot])
        by_card = Counter(obs.card_id for obs in history)
        candidate, votes = by_card.most_common(1)[0]
        candidate_observations = [obs for obs in history if obs.card_id == candidate]
        mean_confidence = sum(obs.confidence for obs in candidate_observations) / len(
            candidate_observations
        )

        if votes >= self.config.min_valid_votes and mean_confidence >= self.config.card_lock_confidence:
            best = max(candidate_observations, key=lambda obs: obs.confidence)
            self._locked[slot] = LockedSlot(best, votes, mean_confidence, 0)
