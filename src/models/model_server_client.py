from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelVersion:
    name: str
    version: str

    def key(self) -> str:
        return self.name.replace("-", "_")
