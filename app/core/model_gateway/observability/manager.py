from __future__ import annotations

from typing import Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.interfaces import TracerProvider
from app.core.model_gateway.observability.logger import StructuredLogger
from app.core.model_gateway.observability.metrics import MetricsRegistry
from app.core.model_gateway.observability.providers.noop import NoopTracer


class ObservabilityManager:
    def __init__(self, config: ObservabilityConfig) -> None:
        self.config = config
        self.logger = StructuredLogger(config)
        self.metrics = MetricsRegistry(config)
        self.tracer: TracerProvider = self._build_tracer(config)

    @staticmethod
    def _build_tracer(config: ObservabilityConfig) -> TracerProvider:
        if not config.enabled or not config.tracing_enabled:
            return NoopTracer()

        provider = config.tracing_provider
        if provider == "otel":
            from app.core.model_gateway.observability.providers.otel.tracer import OTelTracer

            return OTelTracer(config)
        if provider == "langfuse":
            from app.core.model_gateway.observability.providers.langfuse.tracer import LangfuseTracer

            return LangfuseTracer(config)
        if provider == "goml_tracer":
            from app.core.model_gateway.observability.providers.goml_tracer.tracer import get_goml_engine

            return get_goml_engine(config)
        return NoopTracer()

    def shutdown(self) -> None:
        self.tracer.shutdown()


_manager: Optional[ObservabilityManager] = None


def get_manager(config: Optional[ObservabilityConfig] = None) -> ObservabilityManager:
    global _manager
    if _manager is None:
        cfg = config or ObservabilityConfig.from_env()
        _manager = ObservabilityManager(cfg)
    return _manager


def init(config: Optional[ObservabilityConfig] = None) -> ObservabilityManager:
    global _manager
    cfg = config or ObservabilityConfig.from_env()
    _manager = ObservabilityManager(cfg)
    return _manager


def reset_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.shutdown()
    _manager = None
    from app.core.model_gateway.observability.providers.goml_tracer.tracer import reset_goml_singletons

    reset_goml_singletons()
