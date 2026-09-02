from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from app.core.model_gateway.observability.providers.goml_tracer.engine.span import GoMLSpan

_current_span: ContextVar[Optional[GoMLSpan]] = ContextVar("goml_current_span", default=None)


def get_current_span() -> Optional[GoMLSpan]:
    return _current_span.get()


def set_current_span(span: Optional[GoMLSpan]) -> None:
    _current_span.set(span)
