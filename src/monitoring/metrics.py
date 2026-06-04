from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class MetricsRegistry:
    counters: Counter[str] = field(default_factory=Counter)

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def render_prometheus(self) -> str:
        return "\n".join(f"{name} {value}" for name, value in sorted(self.counters.items()))
