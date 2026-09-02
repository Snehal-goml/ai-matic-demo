from __future__ import annotations

from typing import Any, Optional


def build_span_exporter(
    *,
    exporter_name: str,
    endpoint: Optional[str],
) -> Any:
    exporter_name = (exporter_name or "console").lower()
    if exporter_name in ("console",):
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()

    if exporter_name in ("otlp_grpc", "grpc", "otlp"):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)

    if exporter_name in ("otlp_http", "http"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter(endpoint=endpoint)

    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return ConsoleSpanExporter()
