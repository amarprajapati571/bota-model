from __future__ import annotations

from dataclasses import dataclass, field

from src.api.schemas import RoundEvent


@dataclass
class InMemoryRoundRepository:
    rounds: dict[str, RoundEvent] = field(default_factory=dict)

    def upsert_round(self, event: RoundEvent) -> None:
        self.rounds[event.round_id] = event

    def latest_for_table(self, table_id: str) -> RoundEvent | None:
        candidates = [event for event in self.rounds.values() if event.table_id == table_id]
        return max(candidates, key=lambda event: event.ended_at_utc or event.started_at_utc, default=None)
