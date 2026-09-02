# goML Tracer setup and integration (model_gateway)

This guide explains how to enable **goML_tracer** — self-hosted, SQLite-backed distributed tracing for the AI Matic Model Gateway — query traces with the **Python API**, browse them in the **React dashboard**, optionally **replay spans to OTLP**, and deploy on **AWS** (EC2, ECS).

---

## Table of contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Install Python dependencies](#install-python-dependencies)
4. [Configure model_gateway](#configure-model_gateway)
5. [Run and verify](#run-and-verify)
6. [Query traces (Python API)](#query-traces-python-api)
7. [Web dashboard (React UI)](#web-dashboard-react-ui)
8. [Integration patterns](#integration-patterns)
9. [Span data reference](#span-data-reference)
10. [Optional: export to OpenTelemetry](#optional-export-to-opentelemetry)
11. [Production notes](#production-notes)
12. [Deploy on AWS (EC2, ECS)](#deploy-on-aws-ec2-ecs)
13. [Troubleshooting](#troubleshooting)
14. [Related files](#related-files)

---

## How it works

```text
Your app
   │
   ▼
model_gateway.completion() / acompletion()
   │
   ▼
observability.hooks (automatic)
   │
   ▼
GoMLTracerEngine  ──writes──►  SQLite (GOML_TRACER_DB_PATH)
   │
   ├── Python query API  (list_traces, get_span_tree, stats, recent_errors)
   ├── FastAPI dashboard  (port 9090, optional React UI)
   └── Optional OTLP replay  (export stored spans to Jaeger/Tempo)
```

- Tracing is **automatic** on every `completion()` call when observability is enabled and `TRACING_PROVIDER=goml_tracer`.
- Implementation: [`providers/goml_tracer/engine/`](providers/goml_tracer/engine/), [`providers/goml_tracer/storage/sqlite.py`](providers/goml_tracer/storage/sqlite.py).
- One **root span** per completion: `model_gateway.completion` (name from `hooks.py`).
- **No external services** — traces live in a local SQLite file. Ideal for air-gapped, offline, or private deployments.
- Unlike Langfuse or Jaeger, you do **not** need Docker for tracing itself (Docker is optional only if you export to OTLP later).

### Architecture

```text
┌─────────────────────┐     ┌──────────────────────────┐
│  model_gateway       │     │  goml_tracer.db (SQLite)  │
│  TRACING_PROVIDER=   │────►│  spans table + metadata   │
│  goml_tracer         │     └────────────┬─────────────┘
└─────────────────────┘                  │
                                         ▼
                              ┌──────────────────────┐
                              │  Dashboard API :9090  │
                              │  + React UI :5173     │
                              └──────────────────────┘
```

---

## Prerequisites

- Python 3.10+ with `model_gateway` installed (`pip install -r requirements.txt`)
- API keys for your LLM providers (OpenAI, Bedrock, etc.) as usual
- **Writable path** for `GOML_TRACER_DB_PATH` (directory is created automatically)
- **Node.js 18+** (optional) — only for the React dashboard dev server or UI build
- **No** Langfuse account, **no** OTLP collector, **no** Jaeger — unless you use the optional OTLP replay bridge

---

## Install Python dependencies

### Tracing only (goML_tracer)

goML_tracer uses Python’s built-in **`sqlite3`**. You do **not** need `requirements.txt` for writing spans.

### Dashboard API + UI

The FastAPI dashboard needs extras from `requirements.txt`:

```bash
pip install -r requirements.txt
```

| Package | Purpose |
|---------|---------|
| `fastapi`, `uvicorn` | Dashboard HTTP API |
| `opentelemetry-*` | Optional OTLP replay only |

---

## Configure model_gateway

Add to your repo root `.env` (or inject via ECS/SSM). **Never commit production databases with sensitive prompt data.**

### Minimum

```env
# --- Observability master switch ---
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=goml_tracer

# --- goML Tracer storage ---
GOML_TRACER_DB_PATH=./data/goml_tracer.db
GOML_TRACER_RETENTION_DAYS=30
GOML_TRACER_SAMPLING_RATE=1.0

# --- Recommended logging (works alongside tracing) ---
REQUEST_LOGGING_ENABLED=true
RESPONSE_LOGGING_ENABLED=true
LOG_BODIES=false
PII_REDACTION_ENABLED=true
METRICS_ENABLED=true
```

### Capture prompts/completions in span metadata

By default, `TRACING_CAPTURE_IO=true` when observability is enabled. Spans store summarized prompt/completion text in SQLite `metadata_json` (subject to PII redaction).

```env
TRACING_CAPTURE_IO=true
PII_REDACTION_ENABLED=true
```

Set `TRACING_CAPTURE_IO=false` in production if you do not want prompts stored on disk.

### All goML-related variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_ENABLED` | `false` | Master switch for hooks, logging, metrics |
| `TRACING_ENABLED` | same as above | Enable tracing |
| `TRACING_PROVIDER` | `noop` | Must be `goml_tracer` for this guide |
| `GOML_TRACER_DB_PATH` | `./data/goml_tracer.db` | SQLite file path (parent directory created automatically) |
| `GOML_TRACER_RETENTION_DAYS` | `30` | Delete spans older than N days on tracer `shutdown()` |
| `GOML_TRACER_SAMPLING_RATE` | `1.0` | `1.0` = all spans; `0.1` ≈ 10% sampled |
| `TRACING_CAPTURE_IO` | `true` | Store `gen_ai.prompt` / `gen_ai.completion` in span metadata |
| `PII_REDACTION_ENABLED` | `true` | Redact sensitive fields before storage |
| `LOG_BODIES` | `false` | Also enables I/O capture when `TRACING_CAPTURE_IO` is unset |
| `REQUEST_LOGGING_ENABLED` | `true` | JSON request logs on stderr |
| `RESPONSE_LOGGING_ENABLED` | `true` | JSON response logs on stderr |
| `METRICS_ENABLED` | `true` | In-process counters (separate from dashboard stats) |

### Dashboard API variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOML_DASHBOARD_HOST` | `127.0.0.1` | Bind address for `python -m ...dashboard` |
| `GOML_DASHBOARD_PORT` | `9090` | HTTP port |
| `GOML_DASHBOARD_API_KEY` | (empty) | If set, require `X-API-Key` on `/api/*` |
| `GOML_DASHBOARD_CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated origins for dev UI |
| `GOML_DASHBOARD_SERVE_UI` | `false` | Serve built React app from `ui/goml-tracer-dashboard/dist` |

### React UI (Vite) variables

| Variable | Description |
|----------|-------------|
| `VITE_GOML_API_URL` | API base URL (empty = Vite proxy or same origin) |
| `VITE_GOML_API_KEY` | Sent as `X-API-Key` when calling the API |

### Programmatic config (no `.env`)

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig

init(
    ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="goml_tracer",
        goml_tracer_db_path="./data/goml_tracer.db",
        goml_tracer_retention_days=30,
        goml_tracer_sampling_rate=1.0,
        tracing_capture_io=False,
        pii_redaction_enabled=True,
        log_bodies=False,
    )
)
```

Call `init()` **before** the first `completion()` if you use programmatic config.

---

## Run and verify

### 1. Enable tracing in `.env`

Use the [minimum `.env`](#minimum) block above.

### 2. Run a completion

```python
from dotenv import load_dotenv

load_dotenv()

from model_gateway.aim_main import completion

resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Say hello in one word."}],
    custom_llm_provider="openai",
)
print(resp)
```

### 3. Confirm the database file exists

```powershell
# Windows
dir .\data\goml_tracer.db

# Linux / macOS
ls -la ./data/goml_tracer.db
```

### 4. Quick Python check

```python
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api

api = get_goml_query_api(ObservabilityConfig.from_env())
print(api.list_traces(limit=5))
print(api.stats())
```

You should see at least one trace with `span_count >= 1`.

### 5. Shutdown and retention (optional)

Retention runs when the tracer shuts down:

```python
from model_gateway.observability import get_manager

get_manager().shutdown()
```

---

## Query traces (Python API)

```python
from dotenv import load_dotenv

load_dotenv()

from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api

cfg = ObservabilityConfig.from_env()
init(cfg)
api = get_goml_query_api(cfg)

# Recent traces (newest first)
traces = api.list_traces(limit=20, offset=0)
for t in traces:
    print(t["trace_id"], t["span_count"], t.get("error_count", 0))

# Full span tree for one trace
if traces:
    trace_id = traces[0]["trace_id"]
    for span in api.get_span_tree(trace_id):
        print(span.name, span.status, span.duration_ms, span.provider, span.model)

# Aggregated stats
stats = api.stats()
print(stats["summary"])
print(stats["by_provider_model"])

# Recent failed spans
for err in api.recent_errors(limit=10):
    print(err.name, err.error_message)
```

### API methods

| Method | Returns |
|--------|---------|
| `list_traces(limit=50, offset=0)` | Trace summaries: `trace_id`, `start_time`, `end_time`, `span_count`, `error_count` |
| `get_span_tree(trace_id)` | All `SpanRecord` rows for the trace, ordered by `start_time` |
| `stats()` | `summary` (totals, avg duration, tokens, errors) and `by_provider_model` breakdown |
| `recent_errors(limit=50)` | Spans with `status != 'ok'` |

---

## Web dashboard (React UI)

Browse traces in a browser: **Overview**, **Traces**, **Trace detail** (span tree), **Errors**.

### Development (two terminals)

**Terminal 1 — API** (reads the same `GOML_TRACER_DB_PATH` as model_gateway):

```bash
pip install -r requirements.txt

# Windows
set GOML_TRACER_DB_PATH=./data/goml_tracer.db
python -m model_gateway.observability.providers.goml_tracer.dashboard

# Linux / macOS
export GOML_TRACER_DB_PATH=./data/goml_tracer.db
python -m model_gateway.observability.providers.goml_tracer.dashboard
```

API health: http://127.0.0.1:9090/api/health

**Terminal 2 — React dev server**

```bash
cd ui/goml-tracer-dashboard
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` → http://127.0.0.1:9090.

If you set `GOML_DASHBOARD_API_KEY`, also set `VITE_GOML_API_KEY` in `ui/goml-tracer-dashboard/.env.local`.

### Production (single server)

Build the UI once, then serve it from FastAPI:

```bash
cd ui/goml-tracer-dashboard
npm install
npm run build
cd ../..

# Windows
set GOML_TRACER_DB_PATH=./data/goml_tracer.db
set GOML_DASHBOARD_SERVE_UI=true
set GOML_DASHBOARD_HOST=0.0.0.0
python -m model_gateway.observability.providers.goml_tracer.dashboard

# Linux / macOS
export GOML_TRACER_DB_PATH=./data/goml_tracer.db
export GOML_DASHBOARD_SERVE_UI=true
export GOML_DASHBOARD_HOST=0.0.0.0
python -m model_gateway.observability.providers.goml_tracer.dashboard
```

Open http://127.0.0.1:9090 (or your host/port).

### HTTP API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | DB path, schema version, health status |
| `GET` | `/api/stats` | Aggregated metrics |
| `GET` | `/api/traces?limit=&offset=` | Trace list |
| `GET` | `/api/traces/{trace_id}` | Trace summary + all spans |
| `GET` | `/api/traces/{trace_id}/spans` | Spans only |
| `GET` | `/api/errors?limit=` | Recent error spans |

All `/api/*` routes accept optional header `X-API-Key` when `GOML_DASHBOARD_API_KEY` is set.

More UI details: [`ui/goml-tracer-dashboard/README.md`](../../ui/goml-tracer-dashboard/README.md).

---

## Integration patterns

### FastAPI / ASGI app

`observe_async` wraps `acompletion` the same way as sync calls. Ensure `init(ObservabilityConfig.from_env())` runs at startup and `get_manager().shutdown()` on app shutdown.

### Multiple workers (gunicorn / uvicorn workers)

Each worker process has its own SQLite writer unless you use a **shared database path on shared storage** (e.g. EFS). For high concurrency, prefer:

- One writer process + dashboard reader, or
- `TRACING_PROVIDER=otel` with a central collector, or
- Lower `GOML_TRACER_SAMPLING_RATE`

SQLite handles moderate single-host traffic well; avoid many concurrent writers to the same file.

### Switching from another provider

```env
TRACING_PROVIDER=goml_tracer
GOML_TRACER_DB_PATH=./data/goml_tracer.db
```

Previous OTEL/Langfuse env vars are ignored while `goml_tracer` is active.

### Switching to OTEL or Langfuse later

```env
TRACING_PROVIDER=otel
# or
TRACING_PROVIDER=langfuse
```

Existing SQLite data remains on disk; use the [OTLP replay](#optional-export-to-opentelemetry) bridge or keep the dashboard for historical traces.

---

## Span data reference

Each completion creates one root span (child spans are supported by the engine for nested work).

| Field | Source |
|-------|--------|
| `name` | `model_gateway.completion` |
| `trace_id` | UUID (shared by parent/child spans) |
| `provider` / `model` | Resolved LLM provider and model (Bedrock ARN → `bedrock`) |
| `tokens_input` / `tokens_output` | From response `usage` (incl. Bedrock-style keys) |
| `cost` | When available on the completion event |
| `duration_ms` | Wall time from span start to `end()` |
| `status` | `ok` or `error` |
| `error_message` | Set on `record_error()` |
| `metadata` (JSON) | All span attributes: `gen_ai.*`, `correlation_id`, `latency_ms`, `gen_ai.prompt`, `gen_ai.completion`, etc. |

### Common metadata keys (when I/O capture enabled)

| Key | Description |
|-----|-------------|
| `gen_ai.system` | Provider (`openai`, `bedrock`, …) |
| `gen_ai.request.model` | Model id or ARN |
| `gen_ai.usage.input_tokens` | Prompt tokens |
| `gen_ai.usage.output_tokens` | Completion tokens |
| `gen_ai.prompt` | Summarized messages (redacted if configured) |
| `gen_ai.completion` | Assistant text (truncated to 8000 chars) |
| `correlation_id` | Request correlation id |
| `observability.schema_version` | `3` |

**Bedrock:** Pass a Bedrock ARN or `custom_llm_provider=bedrock`. Token counts appear when the response includes `usage` (mapped in `providers/bedrock.py`).

---

## Optional: export to OpenTelemetry

Replay spans from SQLite to any OTLP backend (Jaeger, Tempo, etc.):

```python
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api
from model_gateway.observability.providers.goml_tracer.exporters.otel_exporter import (
    export_spans_to_otel,
)

cfg = ObservabilityConfig.from_env()
api = get_goml_query_api(cfg)
trace_id = api.list_traces(limit=1)[0]["trace_id"]
spans = api.get_span_tree(trace_id)

ok = export_spans_to_otel(spans)
print("exported" if ok else "install opentelemetry packages")
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT` (and related OTEL env vars) before calling. See [`OPENTELEMETRY.md`](OPENTELEMETRY.md) for a full OTEL stack.

---

## Production notes

1. **Back up** `GOML_TRACER_DB_PATH` if traces are required for audit or debugging.
2. Use **`GOML_TRACER_SAMPLING_RATE < 1.0`** under high traffic (e.g. `0.1`).
3. Keep **`LOG_BODIES=false`** and consider **`TRACING_CAPTURE_IO=false`** so prompts are not persisted.
4. Keep **`PII_REDACTION_ENABLED=true`** when storing any message content.
5. Run **retention** via periodic restarts (`shutdown()` applies `GOML_TRACER_RETENTION_DAYS`) or call `engine.store.apply_retention(days)` from a scheduled job.
6. Protect the **dashboard** with `GOML_DASHBOARD_API_KEY`; do not expose port 9090 on the public internet without auth.
7. Prefer **EFS or EBS** for the DB path on AWS when the gateway and dashboard share traces (see below).
8. goML_tracer complements **structured logs** and **in-process metrics** (`get_manager().metrics.snapshot()`); it is not a full APM replacement.

---

## Deploy on AWS (EC2, ECS)

No outbound tracing SaaS is required. Persist the SQLite file on durable storage and run the dashboard as a sidecar or separate service.

### Recommended topology

```text
┌─────────────────────────────────────────────────────────────┐
│  ECS / EC2                                                   │
│  ┌──────────────────┐      ┌─────────────────────────────┐  │
│  │  model_gateway    │      │  Amazon EFS (optional)       │  │
│  │  TRACING_PROVIDER=│─────►│  /data/goml_tracer.db        │  │
│  │  goml_tracer      │      └──────────────┬──────────────┘  │
│  └──────────────────┘                     │                  │
│  ┌──────────────────┐                     │                  │
│  │  Dashboard API    │◄────────────────────┘                  │
│  │  :9090 (internal) │                                        │
│  └──────────────────┘                                        │
└─────────────────────────────────────────────────────────────┘
```

### Shared configuration

```bash
pip install -r requirements.txt
# Dashboard only:
pip install -r requirements.txt
```

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=goml_tracer
GOML_TRACER_DB_PATH=/mnt/efs/goml_tracer.db
GOML_TRACER_RETENTION_DAYS=14
GOML_TRACER_SAMPLING_RATE=0.25

LOG_BODIES=false
TRACING_CAPTURE_IO=false
PII_REDACTION_ENABLED=true
```

### ECS task (conceptual)

- **Volume:** EFS mount at `/mnt/efs` shared by gateway container and dashboard container.
- **Gateway container:** same image as today; env above.
- **Dashboard container:** `python -m model_gateway.observability.providers.goml_tracer.dashboard` with `GOML_DASHBOARD_SERVE_UI=true`, internal ALB only.
- **Secrets:** optional `GOML_DASHBOARD_API_KEY` in Secrets Manager.

### EC2

- Install app on instance; set `GOML_TRACER_DB_PATH` to a path on an attached EBS volume.
- Run dashboard via **systemd** or **supervisor** on localhost; access via SSM port forward or internal ALB.
- Snapshot EBS or copy `.db` for backups.

### Lambda

Lambda is a poor fit for SQLite tracing (ephemeral disk, concurrent invocations). Prefer **`TRACING_PROVIDER=otel`** or **Langfuse Cloud** for Lambda. If you must use goML on Lambda, use `/tmp` only for debugging and accept that traces are lost between cold starts.

### Shutdown

```python
from model_gateway.observability import get_manager

def shutdown_observability() -> None:
    get_manager().shutdown()  # applies retention on goML engine
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Empty `list_traces()` | Set `OBSERVABILITY_ENABLED=true`, `TRACING_PROVIDER=goml_tracer`; run at least one `completion()`; confirm `GOML_TRACER_DB_PATH` matches between writer and reader |
| Dashboard shows no traces | Dashboard must use the **same** `GOML_TRACER_DB_PATH` as the gateway process |
| Permission error on DB | Ensure the process user can create/write the parent directory of `GOML_TRACER_DB_PATH` |
| Database grows large | Lower `GOML_TRACER_RETENTION_DAYS`, reduce `GOML_TRACER_SAMPLING_RATE`, disable `TRACING_CAPTURE_IO` |
| Missing prompts in UI | Set `TRACING_CAPTURE_IO=true` (or `LOG_BODIES=true`); check PII redaction did not remove all fields |
| `database: missing` on `/api/health` | No spans written yet, or wrong DB path — run a completion first |
| `401` on dashboard API | Set `X-API-Key` header to match `GOML_DASHBOARD_API_KEY` |
| CORS errors in dev UI | Add your origin to `GOML_DASHBOARD_CORS_ORIGINS` |
| SQLite locked / database is locked | Too many concurrent writers — reduce workers or use OTEL instead |
| Bedrock shows wrong provider | Use Bedrock ARN; see [`OPENTELEMETRY.md`](OPENTELEMETRY.md) Bedrock notes (same hooks apply) |

---

## Related files

| Path | Role |
|------|------|
| [`providers/goml_tracer/engine/tracer.py`](providers/goml_tracer/engine/tracer.py) | Span creation, sampling |
| [`providers/goml_tracer/engine/span.py`](providers/goml_tracer/engine/span.py) | Persist span lifecycle |
| [`providers/goml_tracer/storage/sqlite.py`](providers/goml_tracer/storage/sqlite.py) | SQLite schema and queries |
| [`providers/goml_tracer/query/api.py`](providers/goml_tracer/query/api.py) | Python query API |
| [`providers/goml_tracer/dashboard/`](providers/goml_tracer/dashboard/) | FastAPI routes and server |
| [`providers/goml_tracer/exporters/otel_exporter.py`](providers/goml_tracer/exporters/otel_exporter.py) | Optional OTLP replay |
| [`ui/goml-tracer-dashboard/`](../../ui/goml-tracer-dashboard/) | React UI |
| [`hooks.py`](hooks.py) | Automatic span attributes on completion |
| [`SETUP.md`](SETUP.md) | All providers comparison |
| [`OPENTELEMETRY.md`](OPENTELEMETRY.md) | OTLP / Jaeger guide |
| [`LANGFUSE.md`](LANGFUSE.md) | Langfuse guide |
