from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SpanRecord


def export_spans_to_otel(spans: List["SpanRecord"]) -> bool:
    """
    Optional bridge: forward stored goML spans to an OTLP backend.
    Returns True if export succeeded, False if OTEL packages are unavailable.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError:
        return False

    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    tracer = trace.get_tracer("goml_tracer.replay")

    for rec in spans:
        with tracer.start_as_current_span(rec.name) as span:
            if rec.provider:
                span.set_attribute("gen_ai.system", rec.provider)
            if rec.model:
                span.set_attribute("gen_ai.request.model", rec.model)
            if rec.error_message:
                span.set_attribute("error.message", rec.error_message)
    provider.shutdown()
    return True
