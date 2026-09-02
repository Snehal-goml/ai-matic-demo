# Docker stacks for model_gateway observability

Docker Compose files for **OpenTelemetry (Jaeger)** and **Langfuse** live under `model_gateway/docker/`.

## Recommended: Jaeger Search + Monitor (one command)

Use this stack for **both** the Jaeger **Search** tab (traces) and **Monitor** tab (RED metrics):

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
```

| What | URL |
|------|-----|
| Jaeger UI (Search + Monitor) | http://localhost:16686 — Monitor: **Span Kind = Server** (not Consumer) |

**Monitor empty but Search works?** Change **Span Kind** from Consumer → **Server**. Verify:

```powershell
.\model_gateway\docker\scripts\verify-jaeger-monitor.ps1
```

| Prometheus | http://localhost:9090 |
| OTLP gRPC (send traces here) | `localhost:4317` |

In your app `.env`:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER=otlp_grpc
OTEL_SERVICE_NAME=goml-gateway
```

Stop:

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml down
```

### Verify containers are healthy

```bash
docker ps --filter "name=goml-"
```

All three should show **Up** (not restarting):

- `goml-otel-collector`
- `goml-jaeger`
- `goml-prometheus`

If `goml-otel-collector` keeps restarting, check logs:

```bash
docker logs goml-otel-collector --tail 30
```

A common cause was a bad spanmetrics config (fixed in `otel-collector-config-spm.yaml`).

---

## Legacy: traces only (Search tab)

These compose files are **not** in this repo; use `docker-compose.otel-spm.yml` above for Search + Monitor.

---

See [observability/OPENTELEMETRY.md](../observability/OPENTELEMETRY.md) for full integration steps.

---

## Langfuse (local LLM traces UI)

Run Langfuse on Docker — no Cloud account required (create API keys in the local UI):

```powershell
.\model_gateway\docker\scripts\start-langfuse.ps1
```

```bash
./model_gateway/docker/scripts/start-langfuse.sh
```

| What | URL |
|------|-----|
| Langfuse UI | http://localhost:3000 |

```env
LANGFUSE_HOST=http://localhost:3000
TRACING_PROVIDER=langfuse
```

See [observability/LANGFUSE.md](../observability/LANGFUSE.md) and [langfuse/README.md](langfuse/README.md).
