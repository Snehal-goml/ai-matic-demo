from __future__ import annotations

import random
import uuid
from typing import Any, Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.interfaces import Span, TracerProvider
from app.core.model_gateway.observability.providers.goml_tracer.engine.context import (
    get_current_span,
    set_current_span,
)
from app.core.model_gateway.observability.providers.goml_tracer.engine.span import GoMLSpan
from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SQLiteSpanStore


class GoMLTracerEngine(TracerProvider):
    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._store = SQLiteSpanStore(config.goml_tracer_db_path)
        self._sampling = max(0.0, min(1.0, config.goml_tracer_sampling_rate))

    @property
    def store(self) -> SQLiteSpanStore:
        return self._store

    def _should_sample(self) -> bool:
        if self._sampling >= 1.0:
            return True
        if self._sampling <= 0.0:
            return False
        return random.random() < self._sampling

    def start_span(
        self,
        name: str,
        *,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        if not self._should_sample():
            from app.core.model_gateway.observability.providers.noop import NoopSpan

            return NoopSpan()

        parent_span = parent if isinstance(parent, GoMLSpan) else get_current_span()
        trace_id = parent_span.trace_id if parent_span else str(uuid.uuid4())
        parent_id = parent_span.id if parent_span else None

        provider = None
        model = None
        if attributes:
            provider = attributes.get("provider") or attributes.get("gen_ai.system")
            model = attributes.get("model") or attributes.get("gen_ai.request.model")

        span = GoMLSpan(
            store=self._store,
            trace_id=trace_id,
            name=name,
            parent_id=parent_id,
            provider=str(provider) if provider else None,
            model=str(model) if model else None,
        )
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)

        set_current_span(span)
        return span

    def shutdown(self) -> None:
        deleted = self._store.apply_retention(self._config.goml_tracer_retention_days)
        if deleted:
            pass  # retention applied silently
