from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

_correlation_id: ContextVar[Optional[str]] = ContextVar("mg_correlation_id", default=None)
_trace_id: ContextVar[Optional[str]] = ContextVar("mg_trace_id", default=None)
_call_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("mg_call_context", default=None)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> Optional[str]:
    return _correlation_id.get()


def ensure_correlation_id(existing: Optional[str] = None) -> str:
    cid = existing or get_correlation_id() or new_correlation_id()
    set_correlation_id(cid)
    return cid


def set_trace_id(value: str) -> None:
    _trace_id.set(value)


def get_trace_id() -> Optional[str]:
    return _trace_id.get()


def set_call_context(
    *,
    provider: str,
    model: str,
    retry_count: int = 0,
) -> None:
    _call_context.set({"provider": provider, "model": model, "retry_count": retry_count})


def get_call_context() -> Optional[Dict[str, Any]]:
    return _call_context.get()


def clear_call_context() -> None:
    _call_context.set(None)
