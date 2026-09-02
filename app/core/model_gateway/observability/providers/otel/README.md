# OpenTelemetry provider

Exports spans via OTLP (gRPC or HTTP) or console.

**Full setup guide (Docker, Jaeger, integration):** [`../../OPENTELEMETRY.md`](../../OPENTELEMETRY.md)

## Quick env

```env
TRACING_PROVIDER=otel
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=goml-gateway
OTEL_EXPORTER=otlp_grpc
```

## Docker

```bash
docker pull jaegertracing/all-in-one:1.57
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
```

## Reference

- `litellm/integrations/opentelemetry.py`
- `Dump/docs/my-website/docs/observability/opentelemetry_integration.md`
