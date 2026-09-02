from __future__ import annotations

from app.core.model_gateway.observability.events import StandardCallEvent


class SpanMetricsCollector:
    """Collect per-call metrics for goML aggregator."""

    def __init__(self) -> None:
        self._events: list[StandardCallEvent] = []

    def record(self, event: StandardCallEvent) -> None:
        self._events.append(event)

    def drain(self) -> list[StandardCallEvent]:
        out = list(self._events)
        self._events.clear()
        return out
