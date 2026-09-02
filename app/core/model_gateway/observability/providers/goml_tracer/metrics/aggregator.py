from __future__ import annotations

from typing import Any, Dict

from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SQLiteSpanStore


class MetricsAggregator:
    def __init__(self, store: SQLiteSpanStore) -> None:
        self._store = store

    def stats(self) -> Dict[str, Any]:
        return self._store.aggregate_stats()
