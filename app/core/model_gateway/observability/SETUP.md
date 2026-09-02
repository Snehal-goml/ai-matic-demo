# Observability setup guide

This guide explains how to enable tracing and logging for **model_gateway** using one of three providers:

| Provider | Best for | External services |
|----------|----------|-------------------|
| **OpenTelemetry** (`otel`) | Grafana, Jaeger, Tempo, Datadog, enterprise APM | OTLP collector |
| **Langfuse** (`langfuse`) | LLM prompt debugging, evals, product analytics | Langfuse server |
| **goML_tracer** (`goml_tracer`) | Self-hosted, private/offline, full control | None (SQLite on disk) |

Only **one** provider is active at a time. Set `TRACING_PROVIDER` accordingly.

---

## Prerequisites (all providers)

### 1. Install dependencies

Core gateway (always required):

```bash
pip install -r requirements.txt
```

Observability extras (required for `otel` and `langfuse`; optional for `goml_tracer`):

```bash
pip install -r requirements.txt
```

| Provider | Packages used |
|----------|----------------|
| `otel` | `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-*` |
| `langfuse` | `langfuse` |
| `goml_tracer` | stdlib `sqlite3` only |

### 2. Shared environment variables

These apply regardless of which tracer you choose. Put them in a `.env` file at the repo root (or export in your shell).

```env
# Master switch
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true

# Pick exactly one: otel | langfuse | goml_tracer
TRACING_PROVIDER=goml_tracer

# Structured logging (stderr, JSON lines)
REQUEST_LOGGING_ENABLED=true
RESPONSE_LOGGING_ENABLED=true
LOG_BODIES=false
LOG_LEVEL=info

# PII masking before logs/traces
PII_REDACTION_ENABLED=true
PII_REDACTION_FIELDS=email,phone,token,authorization,api_key,password,ssn

# In-process metrics (latency, tokens, errors by provider/model)
METRICS_ENABLED=true
```

### 3. Load environment in your app

If you use `python-dotenv`:

```python
from dotenv import load_dotenv

load_dotenv()  # before calling completion()
```

Observability config is read from the environment on the first observed `completion()` call, or you can initialize explicitly:

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig

init(ObservabilityConfig.from_env())
```

### 4. Make a completion call

Tracing is automatic—no code changes beyond env config:

```python
from model_gateway.aim_main import completion

resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello"}],
    custom_llm_provider="openai",
)
```

`text_completion()` / `acompletion()` are wrapped the same way.

### 5. Verify unit tests (optional)

```bash
python -m unittest tests.test_model_gateway_observability -v
```

---

## Option A: OpenTelemetry

Send traces to any OTLP-compatible backend (OpenTelemetry Collector, Grafana Tempo, Jaeger, Honeycomb, etc.).

**Dedicated guide:** [OPENTELEMETRY.md](OPENTELEMETRY.md) — Docker Compose, Jaeger UI, `.env` reference, integration, and troubleshooting.

### When to use

- You already run Grafana / Datadog / enterprise observability
- You need vendor-neutral traces across many services
- You want standard `gen_ai.*` span attributes

### Environment

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=otel

OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=goml-gateway

# Exporter type: otlp_grpc (default) | otlp_http | console
OTEL_EXPORTER=otlp_grpc
```

For **HTTP** OTLP (port 4318 on many collectors):

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
OTEL_EXPORTER=otlp_http
```

For **local debugging** (prints spans to stderr):

```env
OTEL_EXPORTER=console
```

### Minimal local stack (Docker)

Example: OpenTelemetry Collector + Jaeger UI.

```yaml
# docker-compose.otel.yml (example — adjust for your environment)
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"   # UI
      - "4317:4317"     # OTLP gRPC
```

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=goml-gateway
TRACING_PROVIDER=otel
```

Open Jaeger UI: http://localhost:16686 — look for service `goml-gateway` and span name `model_gateway.completion`.

### What gets recorded

Each completion creates a span with attributes such as:

- `gen_ai.system` / `provider`
- `gen_ai.request.model` / `model`
- `correlation_id`
- `tokens_input`, `tokens_output`, `latency_ms` (on success)
- `error.type` (on failure)

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `ImportError: opentelemetry` | Run `pip install -r requirements.txt` |
| No spans in backend | Confirm collector is listening on `OTEL_EXPORTER_OTLP_ENDPOINT`; try `OTEL_EXPORTER=console` |
| gRPC vs HTTP mismatch | Use `otlp_grpc` for port 4317, `otlp_http` for HTTP endpoint |

### Reference

- Implementation: `model_gateway/observability/providers/otel/`
- LiteLLM reference: `litellm/integrations/opentelemetry.py`
- Docs: `Dump/docs/my-website/docs/observability/opentelemetry_integration.md`

---

## Option B: Langfuse

Send each LLM call as a Langfuse **trace** with a **generation** (input, output, model, tokens).

**Dedicated guide:** [LANGFUSE.md](LANGFUSE.md) — Langfuse Cloud / self-hosted, UI walkthrough, `.env` reference, AWS (EC2, ECS, Lambda), and troubleshooting.

### When to use

- You want LLM-native UI for prompts and completions
- Teams need prompt versioning, evals, or session debugging
- You run [Langfuse](https://langfuse.com) (cloud or self-hosted)

### Environment

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=langfuse

LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# Optional metadata / SDK environment (see LANGFUSE.md)
# LANGFUSE_PROJECT_NAME=goml-model-gateway
# LANGFUSE_ORGANIZATION_NAME=my-company
# LANGFUSE_ENVIRONMENT=production
```

For **self-hosted** Langfuse:

```env
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

### Self-hosted Langfuse (Docker, local dev)

From repo root:

```powershell
.\model_gateway\docker\scripts\start-langfuse.ps1
```

Opens **http://localhost:3000** (official Langfuse compose — Postgres, ClickHouse, Redis, MinIO). See [LANGFUSE.md](LANGFUSE.md) and [docker/langfuse/README.md](../docker/langfuse/README.md).

Then create API keys in the UI → **Settings → API keys**, and set:

```env
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

### What gets recorded

- Trace per completion (`model_gateway.completion`)
- Generation with redacted messages (when `PII_REDACTION_ENABLED=true`)
- Model, provider metadata, errors on failure

### Troubleshooting

| Issue | Fix |
|-------|-----|
| `ImportError: langfuse` | `pip install -r requirements.txt` |
| `LANGFUSE_PUBLIC_KEY ... must be set` | Set both public and secret keys |
| Nothing in UI | Confirm `LANGFUSE_HOST` matches your instance; check network/firewall |
| Sensitive data in UI | Set `LOG_BODIES=false` and keep `PII_REDACTION_ENABLED=true` |

### Reference

- **Full guide:** [`LANGFUSE.md`](LANGFUSE.md) (Cloud, self-hosted, UI, AWS EC2/ECS/Lambda)
- Implementation: `model_gateway/observability/providers/langfuse/`
- LiteLLM reference: `litellm/integrations/langfuse/`
- Docs: `Dump/docs/my-website/docs/observability/langfuse_integration.md`

---

## Option C: goML_tracer (custom)

Self-hosted tracing stored in **SQLite** on disk, with a Python query API (no external SaaS).

### When to use

- Air-gapped or private infrastructure
- You want full ownership of trace data
- Lightweight deployments without an observability stack
- Offline development and debugging

**Dedicated guide:** [GOML_TRACER.md](GOML_TRACER.md) — SQLite storage, Python query API, React dashboard, OTLP replay, AWS (EC2/ECS), and troubleshooting.

### Environment

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=goml_tracer

GOML_TRACER_DB_PATH=./data/goml_tracer.db
GOML_TRACER_RETENTION_DAYS=30
GOML_TRACER_SAMPLING_RATE=1.0
```

| Variable | Description |
|----------|-------------|
| `GOML_TRACER_DB_PATH` | SQLite file path (parent directory is created automatically) |
| `GOML_TRACER_RETENTION_DAYS` | Delete spans older than N days on tracer shutdown |
| `GOML_TRACER_SAMPLING_RATE` | `1.0` = all spans; `0.1` = ~10% sampled |

### No extra install

goML_tracer uses Python’s built-in `sqlite3`. You do **not** need `requirements.txt` unless you also use OTEL/Langfuse elsewhere.

### Query traces (Python API)

After running completions with tracing enabled:

```python
from dotenv import load_dotenv

load_dotenv()

from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api

cfg = ObservabilityConfig.from_env()
init(cfg)
api = get_goml_query_api(cfg)

# Recent traces
print(api.list_traces(limit=20))

# Full span tree for one trace
traces = api.list_traces(limit=1)
if traces:
    trace_id = traces[0]["trace_id"]
    print(api.get_span_tree(trace_id))

# Aggregated stats
print(api.stats())

# Recent failures
print(api.recent_errors(limit=10))
```

### Web dashboard (React UI)

Browse traces in a browser instead of using the Python API.

**1. Install dashboard dependencies**

```bash
pip install -r requirements.txt
```

**2. Terminal 1 — start API** (port 9090)

```bash
set GOML_TRACER_DB_PATH=./data/goml_tracer.db
python -m model_gateway.observability.providers.goml_tracer.dashboard
```

**3. Terminal 2 — start UI** (dev)

```bash
cd ui/goml-tracer-dashboard
npm install
npm run dev
```

Open http://localhost:5173 — Overview, Traces, span tree detail, Errors.

**Production (API serves built UI)**

```bash
cd ui/goml-tracer-dashboard && npm run build
set GOML_DASHBOARD_SERVE_UI=true
python -m model_gateway.observability.providers.goml_tracer.dashboard
```

Open http://127.0.0.1:9090

| Variable | Default | Description |
|----------|---------|-------------|
| `GOML_DASHBOARD_HOST` | `127.0.0.1` | Bind address |
| `GOML_DASHBOARD_PORT` | `9090` | Port |
| `GOML_DASHBOARD_API_KEY` | (empty) | If set, require `X-API-Key` on `/api/*` |
| `GOML_DASHBOARD_CORS_ORIGINS` | `http://localhost:5173` | Dev CORS |
| `GOML_DASHBOARD_SERVE_UI` | `false` | Serve `ui/goml-tracer-dashboard/dist` |

Full UI docs: [`ui/goml-tracer-dashboard/README.md`](../../ui/goml-tracer-dashboard/README.md)

### Optional: export stored spans to OTLP

Replay spans from SQLite to an OTLP backend:

```python
from model_gateway.observability.providers.goml_tracer.exporters.otel_exporter import (
    export_spans_to_otel,
)

spans = api.get_span_tree(trace_id)
export_spans_to_otel(spans)  # requires opentelemetry packages
```

### Production notes

- **Back up** `GOML_TRACER_DB_PATH` if traces matter for compliance
- Use `GOML_TRACER_SAMPLING_RATE < 1.0` under high traffic
- Keep `LOG_BODIES=false` in production
- Run retention via app restarts (`shutdown()` applies retention) or schedule periodic `apply_retention` on the store

### Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty `list_traces()` | Confirm `OBSERVABILITY_ENABLED=true` and `TRACING_PROVIDER=goml_tracer`; run at least one `completion()` |
| Permission error on DB path | Ensure the process can write to the directory in `GOML_TRACER_DB_PATH` |
| Database grows large | Lower `GOML_TRACER_RETENTION_DAYS` or sampling rate |

### Reference

- **Full guide:** [`GOML_TRACER.md`](GOML_TRACER.md)
- Implementation: `model_gateway/observability/providers/goml_tracer/`
- Query module: `model_gateway/observability/providers/goml_tracer/query/api.py`

---

## Choosing a provider

```text
Need Grafana/Tempo/Jaeger/Datadog?     → TRACING_PROVIDER=otel
Need LLM prompt UI and evals?          → TRACING_PROVIDER=langfuse
Need self-hosted / offline / SQLite?   → TRACING_PROVIDER=goml_tracer
Observability off?                     → OBSERVABILITY_ENABLED=false
```

You can switch providers by changing `TRACING_PROVIDER` and the provider-specific env vars—no code changes required.

---

## Complete `.env` examples

### OpenTelemetry

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=otel
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=goml-gateway
OTEL_EXPORTER=otlp_grpc
REQUEST_LOGGING_ENABLED=true
PII_REDACTION_ENABLED=true
LOG_BODIES=false
METRICS_ENABLED=true
```

### Langfuse

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=http://langfuse:3000
LANGFUSE_PUBLIC_KEY=pk-lf-your-key
LANGFUSE_SECRET_KEY=sk-lf-your-key
REQUEST_LOGGING_ENABLED=true
PII_REDACTION_ENABLED=true
LOG_BODIES=false
METRICS_ENABLED=true
```

### goML_tracer

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=goml_tracer
GOML_TRACER_DB_PATH=./data/goml_tracer.db
GOML_TRACER_RETENTION_DAYS=30
GOML_TRACER_SAMPLING_RATE=1.0
REQUEST_LOGGING_ENABLED=true
PII_REDACTION_ENABLED=true
LOG_BODIES=false
METRICS_ENABLED=true
```

---

## Programmatic configuration (without `.env`)

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig

cfg = ObservabilityConfig(
    enabled=True,
    tracing_enabled=True,
    tracing_provider="goml_tracer",
    goml_tracer_db_path="./data/goml_tracer.db",
    request_logging_enabled=True,
    log_bodies=False,
    pii_redaction_enabled=True,
)
init(cfg)
```

---

## Further reading

- Overview: [`README.md`](README.md)
- Dedicated guides: `OPENTELEMETRY.md`, `LANGFUSE.md`, `GOML_TRACER.md`
- Per-module notes: `providers/otel/README.md`, `providers/langfuse/README.md`, `providers/goml_tracer/README.md`
- Root repo guide: [`../../README.md`](../../README.md)
