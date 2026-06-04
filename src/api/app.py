from __future__ import annotations

from src.storage.db import InMemoryRoundRepository


class App:
    def __init__(self, repository: InMemoryRoundRepository | None = None) -> None:
        self.repository = repository or InMemoryRoundRepository()

    def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    def latest_round(self, table_id: str) -> dict | None:
        event = self.repository.latest_for_table(table_id)
        return event.to_dict() if event else None
