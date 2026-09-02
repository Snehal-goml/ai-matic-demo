from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from app.core.model_gateway.observability.interfaces import Span
from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SQLiteSpanStore


class GoMLSpan(Span):
    def __init__(
        self,
        *,
        store: SQLiteSpanStore,
        trace_id: str,
        name: str,
        parent_id: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._store = store
        self.id = str(uuid.uuid4())
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.name = name
        self.provider = provider
        self.model = model
        self._start = time.time()
        self._attrs: Dict[str, Any] = {}
        self._ended = False
        self._status = "ok"
        self._error: Optional[str] = None
        self._tokens_in: Optional[int] = None
        self._tokens_out: Optional[int] = None
        self._cost: Optional[float] = None

        from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SpanRecord

        self._store.insert_span(
            SpanRecord(
                id=self.id,
                trace_id=self.trace_id,
                parent_id=self.parent_id,
                name=self.name,
                start_time=self._start,
                end_time=None,
                duration_ms=None,
                status="ok",
                error_message=None,
                metadata={},
                provider=self.provider,
                model=self.model,
                tokens_input=None,
                tokens_output=None,
                cost=None,
            )
        )

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value
        if key in ("provider", "gen_ai.system"):
            self.provider = str(value)
        if key in ("model", "gen_ai.request.model"):
            self.model = str(value)
        if key == "tokens_input":
            self._tokens_in = int(value) if value is not None else None
        if key == "tokens_output":
            self._tokens_out = int(value) if value is not None else None
        if key == "cost":
            self._cost = float(value) if value is not None else None

    def record_error(self, err: Exception) -> None:
        self._status = "error"
        self._error = str(err)
        self._attrs["error.type"] = type(err).__name__

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        events = self._attrs.setdefault("events", [])
        events.append({"name": name, "attributes": attributes or {}})

    def end(self) -> None:
        if self._ended:
            return
        self._ended = True
        end = time.time()
        duration_ms = (end - self._start) * 1000.0
        self._store.update_span_end(
            self.id,
            end_time=end,
            duration_ms=duration_ms,
            status=self._status,
            error_message=self._error,
            metadata=self._attrs,
            tokens_input=self._tokens_in,
            tokens_output=self._tokens_out,
            cost=self._cost,
        )
