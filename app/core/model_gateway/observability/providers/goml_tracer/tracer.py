from __future__ import annotations

from typing import Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.providers.goml_tracer.engine.tracer import GoMLTracerEngine
from app.core.model_gateway.observability.providers.goml_tracer.query.api import GoMLQueryAPI


_engine_singleton: Optional[GoMLTracerEngine] = None
_query_api_singleton: Optional[GoMLQueryAPI] = None


def get_goml_engine(config: ObservabilityConfig) -> GoMLTracerEngine:
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = GoMLTracerEngine(config)
    return _engine_singleton


def get_goml_query_api(config: ObservabilityConfig) -> GoMLQueryAPI:
    global _query_api_singleton
    if _query_api_singleton is None:
        _query_api_singleton = GoMLQueryAPI(get_goml_engine(config))
    return _query_api_singleton


def reset_goml_singletons() -> None:
    global _engine_singleton, _query_api_singleton
    _engine_singleton = None
    _query_api_singleton = None
