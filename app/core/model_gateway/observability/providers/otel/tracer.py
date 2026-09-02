from __future__ import annotations

from typing import Any, Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.context import get_correlation_id
from app.core.model_gateway.observability.interfaces import Span, TracerProvider
from app.core.model_gateway.observability.providers.otel.exporter import build_span_exporter


class OTelSpanAdapter:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is None:
            return
        self._span.set_attribute(key, value)

    def record_error(self, err: Exception) -> None:
        if self._span is None:
            return
        from opentelemetry.trace import Status, StatusCode

        self._span.record_exception(err)
        self._span.set_status(Status(StatusCode.ERROR, str(err)))

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        if self._span is None:
            return
        self._span.add_event(name, attributes=attributes or {})

    def end(self) -> None:
        if self._span is not None:
            self._span.end()


class OTelTracer(TracerProvider):
    def __init__(self, config: ObservabilityConfig) -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": config.otel_service_name,
            }
        )
        exporter = build_span_exporter(
            exporter_name=config.otel_exporter,
            endpoint=config.otel_endpoint,
        )
        provider = SDKTracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer("model_gateway")
        self._provider = provider

    def start_span(
        self,
        name: str,
        *,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        from opentelemetry.trace import SpanKind

        otel_span = self._tracer.start_span(name, kind=SpanKind.SERVER)
        adapter = OTelSpanAdapter(otel_span)
        cid = get_correlation_id()
        if cid:
            adapter.set_attribute("correlation_id", cid)
        if attributes:
            for k, v in attributes.items():
                adapter.set_attribute(k, v)
        return adapter

    def shutdown(self) -> None:
        self._provider.shutdown()
