from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class InMemoryMetrics:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    timers_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def incr(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def timing(self, name: str, duration_ms: float) -> None:
        self.timers_ms[name].append(duration_ms)

    def snapshot(self) -> dict:
        return {
            "counters": dict(self.counters),
            "timers": {k: {"count": len(v), "avg_ms": (sum(v) / len(v)) if v else 0.0} for k, v in self.timers_ms.items()},
        }


metrics = InMemoryMetrics()
