from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    def set_attribute(self, key: str, value: Any) -> None: ...

    def record_error(self, err: Exception) -> None: ...

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None: ...

    def end(self) -> None: ...


@runtime_checkable
class TracerProvider(Protocol):
    def start_span(
        self,
        name: str,
        *,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span: ...

    def shutdown(self) -> None: ...


@runtime_checkable
class MetricsProvider(Protocol):
    def inc_request(self, *, provider: str, model: str, success: bool) -> None: ...

    def record_latency(self, *, provider: str, model: str, latency_ms: float) -> None: ...

    def record_tokens(
        self, *, provider: str, model: str, tokens_input: int, tokens_output: int
    ) -> None: ...

    def record_cost(self, *, provider: str, model: str, cost: float) -> None: ...
