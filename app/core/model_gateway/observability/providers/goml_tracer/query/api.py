from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.model_gateway.observability.providers.goml_tracer.engine.tracer import GoMLTracerEngine
from app.core.model_gateway.observability.providers.goml_tracer.metrics.aggregator import MetricsAggregator
from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SpanRecord


class GoMLQueryAPI:
    """Python query API mirroring /internal/traces, /internal/spans, /internal/stats, /internal/errors."""

    def __init__(self, engine: GoMLTracerEngine) -> None:
        self._engine = engine
        self._aggregator = MetricsAggregator(engine.store)

    def list_traces(self, *, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        return self._engine.store.list_traces(limit=limit, offset=offset)

    def get_span_tree(self, trace_id: str) -> List[SpanRecord]:
        return self._engine.store.get_spans_for_trace(trace_id)

    def stats(self) -> Dict[str, Any]:
        return self._aggregator.stats()

    def recent_errors(self, *, limit: int = 50) -> List[SpanRecord]:
        return self._engine.store.recent_errors(limit=limit)
