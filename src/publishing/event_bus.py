from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.api.schemas import RoundEvent


class EventPublisher(Protocol):
    def publish(self, event: RoundEvent) -> None:
        """Publish a structured round event."""


@dataclass
class InMemoryEventPublisher:
    events: list[RoundEvent] = field(default_factory=list)

    def publish(self, event: RoundEvent) -> None:
        self.events.append(event)
