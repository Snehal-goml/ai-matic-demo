from __future__ import annotations

from typing import Any, Optional

from app.core.model_gateway.observability.interfaces import Span, TracerProvider


class NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_error(self, err: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        pass

    def end(self) -> None:
        pass


class NoopTracer(TracerProvider):
    def start_span(
        self,
        name: str,
        *,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        return NoopSpan()

    def shutdown(self) -> None:
        pass
