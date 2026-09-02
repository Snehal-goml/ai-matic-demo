# OpenTelemetry setup and integration (model_gateway)

This guide explains how to enable **OpenTelemetry (OTEL)** tracing for the AI Matic Model Gateway, run a local trace backend with **Docker**, and verify spans in **Jaeger** (or any OTLP-compatible tool).

---

## Table of contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Install Python dependencies](#install-python-dependencies)
4. [Configure model_gateway](#configure-model_gateway)
5. [Docker: local trace backend](#docker-local-trace-backend)
6. [Run and verify](#run-and-verify)
7. [View results in the UI (Jaeger)](#view-results-in-the-ui-jaeger)
8. [Integration patterns](#integration-patterns)
9. [Span data reference](#span-data-reference)
10. [Production notes](#production-notes)
11. [Deploy on AWS (EC2, ECS, Lambda)](#deploy-on-aws-ec2-ecs-lambda)
12. [Troubleshooting](#troubleshooting)
13. [Related files](#related-files)

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
OTelTracer  ──OTLP gRPC/HTTP──►  Collector / Jaeger / Grafana Tempo / Datadog ...
```

- Tracing is **automatic** on every `completion()` call when observability is enabled.
- Implementation: [`providers/otel/tracer.py`](providers/otel/tracer.py), [`providers/otel/exporter.py`](providers/otel/exporter.py).
- One span per completion: **`model_gateway.completion`**.
- LiteLLM reference (patterns only): `litellm/integrations/opentelemetry.py`, `Dump/docs/my-website/docs/observability/opentelemetry_integration.md`.

---

## Prerequisites

- Python 3.10+ with `model_gateway` installed (`pip install -r requirements.txt`)
- API keys for your LLM providers (OpenAI, Bedrock, etc.) as usual
- **Docker Desktop** (or Docker Engine) for local Jaeger/collector (optional but recommended)

---

## Install Python dependencies

OpenTelemetry is an **optional** extra (not in core `requirements.txt`):

```bash
pip install -r requirements.txt
```

Packages used:

| Package | Purpose |
|---------|---------|
| `opentelemetry-api` | Trace API |
| `opentelemetry-sdk` | TracerProvider, batch export |
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP over gRPC (port 4317) |
| `opentelemetry-exporter-otlp-proto-http` | OTLP over HTTP (port 4318) |

---

## Configure model_gateway

Add to your repo root `.env` (or export in the shell). **Use placeholders in shared docs; never commit real API keys.**

### Minimum (OTLP → local Jaeger)

```env
# --- Observability master switch ---
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=otel

# --- OpenTelemetry ---
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=goml-gateway
OTEL_EXPORTER=otlp_grpc

# --- Recommended logging (works alongside OTEL) ---
REQUEST_LOGGING_ENABLED=true
RESPONSE_LOGGING_ENABLED=true
LOG_BODIES=false
TRACING_CAPTURE_IO=true
PII_REDACTION_ENABLED=true
METRICS_ENABLED=true
```

### All supported OTEL-related variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_ENABLED` | `false` | Master switch for hooks, logging, metrics |
| `TRACING_ENABLED` | same as above | Enable tracing |
| `TRACING_PROVIDER` | `noop` | Must be `otel` for this guide |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | Collector/Jaeger OTLP URL |
| `OTEL_SERVICE_NAME` | `goml-gateway` | `service.name` resource attribute |
| `OTEL_EXPORTER` | `otlp_grpc` | `otlp_grpc`, `otlp_http`, or `console` |
| `REQUEST_LOGGING_ENABLED` | `true` | JSON request logs on stderr |
| `RESPONSE_LOGGING_ENABLED` | `true` | JSON response logs on stderr |
| `LOG_BODIES` | `false` | Log full bodies to stderr JSON (off in prod) |
| `TRACING_CAPTURE_IO` | `true` when OTEL on | Put prompt/completion on trace spans (separate from logs) |
| `PII_REDACTION_ENABLED` | `true` | Redact sensitive fields before log/trace payloads |
| `METRICS_ENABLED` | `true` | In-process counters (separate from OTLP metrics) |

### Exporter modes

**gRPC (default)** — Jaeger all-in-one, most collectors on port 4317:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER=otlp_grpc
```

**HTTP** — some cloud backends or HTTP-only collectors:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
OTEL_EXPORTER=otlp_http
```

**Console** — debug without Docker (spans printed to stderr):

```env
OTEL_EXPORTER=console
# OTEL_EXPORTER_OTLP_ENDPOINT not required
```

### Programmatic config (no `.env`)

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig

init(
    ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="otel",
        otel_endpoint="http://localhost:4317",
        otel_service_name="goml-gateway",
        otel_exporter="otlp_grpc",
        log_bodies=False,
        pii_redaction_enabled=True,
    )
)
```

Call `init()` **before** the first `completion()` if you use programmatic config.

---

## Docker: local trace backend (Search + Monitor)

Use **one** compose file for both Jaeger tabs:

| Jaeger tab | What you get |
|------------|----------------|
| **Search** | Individual traces (every `completion()` span) |
| **Monitor** | RED metrics (request rate, errors, latency) per service/operation |

### Recommended stack (Search + Monitor)

From the repo root:

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
```

| Service | URL |
|---------|-----|
| **Jaeger UI** (Search + Monitor) | http://localhost:16686 |
| Prometheus (metrics backend) | http://localhost:9090 |
| OTLP gRPC — **point your app here** | `localhost:4317` |
| OTLP HTTP | `localhost:4318` |

Your `.env` (same endpoint as before — the collector listens on 4317):

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_EXPORTER=otlp_grpc
OTEL_SERVICE_NAME=goml-gateway
```

**Architecture:**

```text
model_gateway  --OTLP:4317-->  otel-collector  --traces-->  Jaeger (Search)
                              \--span metrics-->  Prometheus -->  Jaeger (Monitor)
```

**Verify containers are running** (all should be `Up`, not restarting):

```bash
docker ps --filter "name=goml-"
```

Expected: `goml-otel-collector`, `goml-jaeger`, `goml-prometheus`.

Stop:

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml down
```

> **Note:** Tag `jaegertracing/all-in-one:1.62` does not exist on Docker Hub. This repo uses **`1.57`**.

### After starting: use both Jaeger tabs

1. Run at least one traced `completion()` (see [Run and verify](#run-and-verify)).
2. **Search** — http://localhost:16686 → **Search** → Service `goml-gateway` → Operation `model_gateway.completion` → **Find Traces**.
3. **Monitor** — same URL → **Monitor** → Service `goml-gateway` (metrics may take ~1 minute after first traces).

### Remote OTLP (Grafana Cloud / Honeycomb / Datadog)

Point `OTEL_EXPORTER_OTLP_ENDPOINT` to your vendor. Example (HTTP):

```env
OTEL_EXPORTER=otlp_http
OTEL_EXPORTER_OTLP_ENDPOINT=https://your-vendor-endpoint/v1/traces
```

Vendor Monitor/APM UIs replace Jaeger Monitor for production.

### Verify Monitor metrics (optional)

```powershell
.\model_gateway\docker\scripts\verify-jaeger-monitor.ps1
```

### Legacy Jaeger-only stacks

Older docs referenced separate `docker-compose.otel.yml` files. This repo ships **only** [`docker-compose.otel-spm.yml`](../docker/docker-compose.otel-spm.yml) under `model_gateway/docker/` (Search + Monitor). Do not use a plain Jaeger all-in-one without Prometheus if you need the **Monitor** tab.

---

## Run and verify

### 1. Start Docker (Search + Monitor)

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
docker ps --filter "name=goml-"
```

### 2. Load environment

```python
from dotenv import load_dotenv
load_dotenv()
```

### 3. Call the gateway

```python
from model_gateway.aim_main import completion

resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Say hello in one sentence"}],
    custom_llm_provider="openai",
    max_tokens=60,
)
print(resp.choices[0].message.content)
```

Or use the smoke test script:

```bash
python test_aim_model_gateway.py --providers openai
```

### 4. Quick check without LLM calls

Run observability unit tests (uses in-memory OTEL exporter):

```bash
python -m unittest tests.test_model_gateway_observability.TestOTelInMemory -v
```

---

## View results in the UI (Jaeger)

OpenTelemetry traces from `model_gateway` are viewed in the **Jaeger web UI** (not a separate goML app). You need Jaeger running via Docker (see [Docker](#docker-local-trace-backend)) and at least one `completion()` call after OTEL is enabled.

### Where to open

| What | URL |
|------|-----|
| **Jaeger UI** (trace search & timeline) | **http://localhost:16686** |

Start the stack: `docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d`

### Step-by-step in Jaeger

1. Start Docker: `docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d` and confirm `goml-otel-collector` is **Up** (`docker ps --filter name=goml-`).
2. Run your app with `TRACING_PROVIDER=otel` and call `completion()` (see [Run and verify](#run-and-verify)).
3. Open **http://localhost:16686** in a browser.
4. On the **Search** tab:
   - **Service** → choose `goml-gateway` (must match `OTEL_SERVICE_NAME` in `.env`)
   - **Operation** → choose `model_gateway.completion`
   - Click **Find Traces**
5. Click a trace in the list to open the **trace detail** view:
   - Timeline of spans
   - Tags/attributes: `gen_ai.system`, `gen_ai.request.model`, `latency_ms`, `gen_ai.usage.*`, `correlation_id`
   - With `TRACING_CAPTURE_IO=true` (default for OTEL): `gen_ai.prompt`, `gen_ai.completion`
   - Verify tag `observability.schema_version=3` on new spans (confirms updated gateway code)
   - Errors shown in red if the call failed

### Jaeger **Monitor** tab (RED metrics)

With `docker-compose.otel-spm.yml` running:

1. Open http://localhost:16686 → **Monitor**.
2. **Service** → `goml-gateway` (must match `OTEL_SERVICE_NAME`).
3. **Span Kind** → **`Server`** — **not Consumer** (your screenshot shows Consumer; that filter returns zero metrics).  
   model_gateway emits **server** spans only. Prometheus has `span_kind=SPAN_KIND_SERVER`. Search can work while Monitor looks “broken” if this dropdown is wrong.  
   Jaeger may remember Consumer in browser storage — use a private window or clear site data for `localhost:16686` if it keeps reverting.
4. **Timeframe** → Last 5 minutes (or wider after idle).
5. Run a few more `completion()` calls if charts are still empty; wait ~30s for Prometheus scrape.

**Quick check (PowerShell):**

```powershell
$end = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
# Should return metric points (not empty):
Invoke-RestMethod "http://localhost:16686/api/metrics/calls?service=goml-gateway&spanKind=server&lookback=300000&endTs=$end"
# Consumer filter returns nothing for this app:
Invoke-RestMethod "http://localhost:16686/api/metrics/calls?service=goml-gateway&spanKind=consumer&lookback=300000&endTs=$end"
```

If Monitor still shows “Get started”, you are likely on the legacy Jaeger-only stack — switch to `docker-compose.otel-spm.yml`.

### If the service list is empty (Search)

- Confirm all containers are **Up**: `docker ps --filter name=goml-` (`goml-otel-collector`, `goml-jaeger`, `goml-prometheus`)
- If `goml-otel-collector` is restarting: `docker logs goml-otel-collector --tail 20` (see [Troubleshooting](#troubleshooting))
- Confirm you ran at least one traced completion **after** enabling observability
- Try **Lookback** = “Last hour” on the Search page
- Temporarily set `OTEL_EXPORTER=console` and confirm spans print in your terminal (rules out export issues)

### Other UIs (not Jaeger)

| Backend | Where to view |
|---------|----------------|
| **Jaeger** (this guide) | http://localhost:16686 |
| **Grafana Tempo** | Grafana → Explore → Tempo datasource |
| **Datadog / Honeycomb / etc.** | Your vendor’s APM/trace UI |
| **goML_tracer** (different provider) | [goML React dashboard](../../ui/goml-tracer-dashboard/README.md) — not used when `TRACING_PROVIDER=otel` |

---

## Integration patterns

### Sync and async

Both are instrumented automatically:

```python
from model_gateway.aim_main import completion, acompletion

completion(model="...", messages=[...], custom_llm_provider="openai")
await acompletion(model="...", messages=[...], custom_llm_provider="openai")
```

### Streaming

`stream=True` sets span attribute `stream=true`. Duration covers the full call; per-chunk OTLP events are not emitted in v1.

### Router / retries

When the model router retries providers, the outer span still represents the completion. Failed attempts may be visible via logs; nested retry spans are a future enhancement.

### Correlation ID

Each call gets a `correlation_id` (context variable + span attribute). Propagate from your HTTP layer by setting the context before calling the gateway (advanced: use `model_gateway.observability.context.set_correlation_id`).

### Alongside logging and metrics

With `OBSERVABILITY_ENABLED=true` you also get:

- **Structured JSON logs** (stderr) — independent of Jaeger
- **In-process metrics** — `get_manager().metrics.snapshot()` in Python

OTEL handles **distributed traces**; logs/metrics complement traces in operations.

### Switching away from OTEL

Use another provider without code changes:

```env
TRACING_PROVIDER=langfuse
# or
TRACING_PROVIDER=goml_tracer
```

See [LANGFUSE.md](LANGFUSE.md) for Langfuse and [SETUP.md](SETUP.md) for goML_tracer.

---

## Span data reference

| Attribute | When set | Example |
|-----------|----------|---------|
| `service.name` | Resource | `goml-gateway` |
| Span name | Always | `model_gateway.completion` |
| `gen_ai.system` | End (resolved) | `openai`, `bedrock` — inferred from model ARN or `custom_llm_provider` |
| `gen_ai.request.model` | End (resolved) | Model id or Bedrock ARN |
| `provider`, `model` | End (resolved) | Same as above |
| `stream` | Start | `true` / `false` |
| `call_type` | Start | `completion`, `acompletion` |
| `correlation_id` | Start | UUID |
| `messages` | Start | Request messages (consider PII settings) |
| `gen_ai.prompt` | Start/End | When `TRACING_CAPTURE_IO=true` — serialized messages |
| `gen_ai.completion` | End | When `TRACING_CAPTURE_IO=true` — assistant text |
| `observability.schema_version` | Start | `3` — bump when span schema changes |
| `latency_ms` | Success | `532.4` |
| `tokens_input`, `tokens_output` | Success | From response `usage` |
| `gen_ai.usage.input_tokens` | Success | Same as `tokens_input` |
| `gen_ai.usage.output_tokens` | Success | Same as `tokens_output` |
| `gen_ai.usage.total_tokens` | Success | Sum when both token counts present |
| `cost` | Success | If available |
| `retry_count` | Success | Router retries |
| Exception event | Failure | Recorded via `span.record_exception` |

**Bedrock:** Use a Bedrock model id/ARN or `custom_llm_provider=bedrock`. Token counts require `usage` on the response (mapped from Bedrock Converse `inputTokens` / `outputTokens`).

---

## Production notes

1. **Do not use `LOG_BODIES=true`** in production; keep `PII_REDACTION_ENABLED=true`.
2. Run a managed **OTLP collector** (Grafana Alloy/Agent, Datadog agent, AWS ADOT) instead of Jaeger all-in-one.
3. Set `OTEL_SERVICE_NAME` per environment: `goml-gateway-prod`, `goml-gateway-staging`.
4. Use **sampling** at the collector for high traffic (model_gateway exports all spans when tracing is on).
5. Ensure outbound network access from your app to the collector endpoint (firewall / VPC).
6. On shutdown, call `model_gateway.observability.get_manager().shutdown()` in long-running services to flush batched spans.

---

## Deploy on AWS (EC2, ECS, Lambda)

This section describes how to run **model_gateway** with OpenTelemetry on AWS. The gateway code is the same everywhere; what changes is **where OTLP goes** and **how you view traces**.

### Recommended AWS topology

```text
┌─────────────────────────────────────────────────────────────────┐
│  Your workload (EC2 / ECS task / Lambda)                          │
│  ┌──────────────────────┐                                       │
│  │  model_gateway app    │  OTLP gRPC/HTTP :4317                  │
│  │  (completion/...)     ├──────────────────┐                    │
│  └──────────────────────┘                  ▼                    │
└────────────────────────────────────────────│────────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────┐
                    │  OpenTelemetry Collector (pick one)              │
                    │  • AWS Distro for OpenTelemetry (ADOT) sidecar   │
                    │  • ECS service / EC2 Docker (otel-collector)     │
                    │  • Managed: Grafana Cloud, Datadog, Honeycomb    │
                    └────────────┬───────────────────┬──────────────────┘
                                 │ traces          │ metrics (optional)
                                 ▼                 ▼
                    ┌────────────────────┐  ┌──────────────────┐
                    │ Trace backend       │  │ Prometheus / AMP │
                    │ X-Ray, Tempo,       │  │ (Jaeger Monitor)   │
                    │ Jaeger, vendor APM  │  └──────────────────┘
                    └────────────────────┘
```

**Local dev** uses [`docker/docker-compose.otel-spm.yml`](../docker/docker-compose.otel-spm.yml) (Jaeger + collector + Prometheus). **In AWS**, run the collector/ADOT in your VPC and point `OTEL_EXPORTER_OTLP_ENDPOINT` at it — do not run Jaeger all-in-one in Lambda.

### Shared configuration (all compute types)

Install observability dependencies in the image or layer:

```bash
pip install -r requirements.txt -r requirements.txt
```

Environment variables (use **Secrets Manager** / **SSM Parameter Store** for keys — not plain task env in production):

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=otel
OTEL_SERVICE_NAME=goml-gateway-prod
OTEL_EXPORTER=otlp_grpc
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317

TRACING_CAPTURE_IO=false
LOG_BODIES=false
PII_REDACTION_ENABLED=true
```

Load env **before** the first `completion()`:

```python
from dotenv import load_dotenv
load_dotenv()  # optional on ECS/Lambda if env is injected by the platform

from model_gateway.aim_main import completion
```

Flush spans on shutdown (important for ECS task stop and Lambda freeze):

```python
from model_gateway.observability import get_manager

def shutdown_observability() -> None:
    get_manager().shutdown()
```

| Setting | EC2 / ECS | Lambda |
|---------|-----------|--------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` (sidecar) or `http://otel-collector.namespace:4317` | ADOT extension `http://localhost:4317` or regional collector URL |
| `TRACING_CAPTURE_IO` | `false` in prod unless compliance allows | Prefer `false` (smaller spans, less PII risk) |
| `OTEL_SERVICE_NAME` | Per env: `goml-gateway-staging`, `goml-gateway-prod` | Include function name/version if many functions |

**Security groups / networking:** allow **outbound** TCP `4317` (gRPC) or `4318` (HTTP) from the app subnet to the collector. Do not expose the collector to the public internet without TLS and auth.

---

### EC2 (long-running VM)

Use EC2 when the gateway runs as a persistent API, worker, or batch host.

#### Option A — App + collector on the same instance (simplest)

1. Launch EC2 (Amazon Linux 2023 or Ubuntu) in a private subnet with NAT for outbound LLM APIs.
2. Clone the repo and install Python deps (see [Prerequisites](#prerequisites)).
3. Run the same stack as local dev (Jaeger is OK for internal tools only):

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
```

4. App `.env` on the instance:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
OTEL_SERVICE_NAME=goml-gateway-prod
```

5. Run your service (example):

```bash
# systemd, supervisord, or screen — example one-off test
python test_aim_model_gateway.py --providers bedrock
```

6. Open Jaeger UI via **SSH tunnel** or internal ALB on port `16686` (restrict security group to VPN/bastion).

```bash
ssh -L 16686:127.0.0.1:16686 ec2-user@<instance-ip>
# Browser: http://localhost:16686
```

#### Option B — Production-style EC2 (ADOT or central collector)

1. Run **ADOT Collector** or `otel/opentelemetry-collector-contrib` on EC2 or as a separate ECS service (see [ECS](#ecs-fargate--ec2-launch-type)).
2. Point the app at the collector DNS name.
3. Export traces to **Amazon Managed Service for Prometheus (AMP) + Grafana**, **X-Ray**, or a vendor endpoint — configure in collector config, not in model_gateway.

**systemd example** (app unit) — call shutdown on stop:

```ini
[Service]
ExecStart=/opt/venv/bin/python /opt/app/your_service.py
ExecStop=/bin/kill -TERM $MAINPID
# In your app, register SIGTERM handler that calls get_manager().shutdown()
```

**IAM:** instance role needs `bedrock:InvokeModel` (if using Bedrock), Secrets Manager read for API keys, and (if using X-Ray/AMP) the usual ADOT/X-Ray write policies.

---

### ECS (Fargate or EC2 launch type)

Use ECS when the gateway runs in containers with horizontal scaling.

#### Task layout (recommended): app container + ADOT sidecar

```text
ECS Task
├── container: model-gateway-app     (your image, port 8000 etc.)
└── container: aws-otel-collector    (ADOT or contrib collector image)
         ▲
         └── app sends OTLP to localhost:4317 (awsvpc) or linked container name
```

**Task definition sketch (Fargate, awsvpc):**

```json
{
  "family": "goml-gateway",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "model-gateway",
      "image": "<account>.dkr.ecr.<region>.amazonaws.com/goml-gateway:latest",
      "essential": true,
      "environment": [
        { "name": "OBSERVABILITY_ENABLED", "value": "true" },
        { "name": "TRACING_ENABLED", "value": "true" },
        { "name": "TRACING_PROVIDER", "value": "otel" },
        { "name": "OTEL_EXPORTER", "value": "otlp_grpc" },
        { "name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://127.0.0.1:4317" },
        { "name": "OTEL_SERVICE_NAME", "value": "goml-gateway-prod" },
        { "name": "TRACING_CAPTURE_IO", "value": "false" }
      ],
      "secrets": [
        { "name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..." },
        { "name": "AWS_ACCESS_KEY_ID", "valueFrom": "arn:aws:secretsmanager:..." }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/goml-gateway",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "app"
        }
      }
    },
    {
      "name": "aws-otel-collector",
      "image": "public.ecr.aws/aws-observability/aws-otel-collector:latest",
      "essential": true,
      "command": ["--config=/etc/ecs/ecs-default-config.yaml"],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/goml-gateway",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "otel"
        }
      }
    }
  ]
}
```

Mount a **custom ADOT config** for X-Ray, AMP, or OTLP forward to your vendor (replace `ecs-default-config.yaml` via EFS or baked image). For Jaeger-style **Search + Monitor** in AWS, run collector + Prometheus + Jaeger as a separate ECS service using [`docker-compose.otel-spm.yml`](../docker/docker-compose.otel-spm.yml) on EC2/ECS EC2 launch type, or use Grafana Cloud instead.

#### Separate collector ECS service

If the collector is its own service behind Service Discovery:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.goml.local:4317
```

Register `otel-collector` in Cloud Map; security group: allow `4317` from the app service security group only.

#### Dockerfile snippet (app image)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements.txt
COPY . .
ENV OBSERVABILITY_ENABLED=true TRACING_PROVIDER=otel
CMD ["python", "-m", "uvicorn", "your_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

On **SIGTERM** (ECS task stop), flush traces in your web framework lifespan or signal handler:

```python
import signal
from model_gateway.observability import get_manager

def _term(*_args):
    get_manager().shutdown()

signal.signal(signal.SIGTERM, _term)
```

#### Viewing traces (ECS)

| Backend | Where to look |
|---------|----------------|
| ADOT → **X-Ray** | AWS Console → CloudWatch → X-Ray traces |
| ADOT → **AMP + Grafana** | Amazon Managed Grafana dashboards |
| Self-hosted Jaeger on EC2/ECS | Jaeger UI (internal ALB), Monitor → **Span Kind = Server** |
| Datadog / Honeycomb / etc. | Vendor UI; set `OTEL_EXPORTER_OTLP_ENDPOINT` in collector export |

---

### Lambda

Use Lambda for short, event-driven calls to `completion()` / `acompletion()`. Tracing works, but you must **flush before the invocation ends** or spans may be lost.

#### Constraints

| Topic | Guidance |
|-------|----------|
| Cold start | First span after cold start may add latency; keep `TRACING_CAPTURE_IO=false` |
| Timeout | LLM + export must fit inside function timeout; collector should be in-VPC or use ADOT layer |
| Async | `acompletion` is fine; still flush before return |
| Streaming | Supported; flush after stream completes |
| Jaeger on Lambda | **Not supported** — use X-Ray or a SaaS backend |

#### Option A — ADOT Lambda layer (recommended on AWS)

1. Attach the [AWS Distro for OpenTelemetry Lambda layer](https://aws-otel.github.io/docs/getting-started/lambda) for your runtime (Python 3.11, etc.).
2. Set environment variables on the function:

```env
AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument
OTEL_SERVICE_NAME=goml-gateway-lambda
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=otel
OTEL_EXPORTER=otlp_grpc
TRACING_CAPTURE_IO=false
```

3. Enable **active tracing** or configure the layer to export to **X-Ray** (console → Lambda → Configuration → Monitoring).

4. Package `model_gateway` + `requirements.txt` in the deployment zip/image.

#### Option B — model_gateway OTEL only (no layer auto-instrument)

Use the gateway’s built-in tracer and point OTLP at a collector reachable from Lambda (VPC + NAT, or HTTP exporter to a public ingest URL with auth):

```python
import os
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability import get_manager
from model_gateway.aim_main import completion

# Module-level init (runs once per execution environment)
init(
    ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="otel",
        otel_endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"],
        otel_service_name=os.environ.get("OTEL_SERVICE_NAME", "goml-gateway-lambda"),
        otel_exporter=os.environ.get("OTEL_EXPORTER", "otlp_grpc"),
        tracing_capture_io=False,
        pii_redaction_enabled=True,
    )
)


def handler(event, context):
    try:
        resp = completion(
            model=event["model"],
            messages=event["messages"],
            custom_llm_provider=event.get("provider"),
            max_tokens=event.get("max_tokens", 256),
        )
        return {"statusCode": 200, "body": str(resp)}
    finally:
        get_manager().shutdown()  # required: flush batched spans before freeze
```

**Lambda in a VPC:** place the function in private subnets with NAT for Bedrock/OpenAI; run ADOT collector or NLB-target collector in the same VPC; security group outbound to `4317`.

#### Lambda container image

```dockerfile
FROM public.ecr.aws/lambda/python:3.11
COPY requirements.txt requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r requirements.txt -r requirements.txt
COPY model_gateway ${LAMBDA_TASK_ROOT}/model_gateway/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_handler.handler"]
```

Increase **memory** (e.g. 1024 MB+) for faster cold starts when using OTEL + Bedrock.

#### Viewing traces (Lambda)

- **X-Ray:** Service map and trace details for `OTEL_SERVICE_NAME` / function name.
- **CloudWatch Logs:** JSON request/response logs from `REQUEST_LOGGING_ENABLED` (separate from traces).
- **Vendor APM:** Point ADOT or `OTEL_EXPORTER_OTLP_ENDPOINT` to Honeycomb/Datadog ingest URL.

---

### AWS deployment checklist

| Step | EC2 | ECS | Lambda |
|------|-----|-----|--------|
| Install `requirements.txt` | Yes | In image | In zip/image/layer |
| Set `OBSERVABILITY_ENABLED` + `TRACING_PROVIDER=otel` | Yes | Task env | Function env |
| OTLP reachable (SG / VPC / NAT) | Yes | Yes | VPC or public ingest |
| `get_manager().shutdown()` on stop | systemd / SIGTERM | SIGTERM / lifespan | **`finally` in handler** |
| PII: `TRACING_CAPTURE_IO=false` | Prod | Prod | Strongly recommended |
| Bedrock / OpenAI IAM or secrets | Instance role / env | Task role + Secrets Manager | Function role + Secrets Manager |
| Trace UI | Jaeger (dev), X-Ray/Grafana (prod) | Same | X-Ray / vendor (not Jaeger) |

### Reusing the local Jaeger stack in AWS (dev/staging only)

For a **non-production** environment you can run [`docker-compose.otel-spm.yml`](../docker/docker-compose.otel-spm.yml) on a small EC2 instance or ECS EC2 host:

```bash
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
```

Point staging apps at `http://<internal-host>:4317`. Use an internal ALB for port `16686` and remember **Monitor → Span Kind = Server**. For production, prefer ADOT + X-Ray/AMP or your observability vendor.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `ImportError: opentelemetry` | Missing optional deps | `pip install -r requirements.txt` |
| No traces in Jaeger | Docker not running or wrong port | `docker ps`, verify `4317` published |
| No traces in Jaeger | Wrong exporter protocol | gRPC → port 4317 + `otlp_grpc`; HTTP → 4318 + `otlp_http` |
| `OBSERVABILITY_ENABLED` ignored | Env not loaded | `load_dotenv()` before imports/calls |
| Spans only in console | `OTEL_EXPORTER=console` | Set `otlp_grpc` and endpoint |
| Empty Jaeger service list | No completions yet | Run at least one traced `completion()` |
| Connection refused on 4317 | Collector not up | `docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d` |
| `goml-otel-collector` restart loop | Bad collector config | `docker logs goml-otel-collector`; fixed: no duplicate `service.name` in spanmetrics |
| Monitor tab “Get started” | Wrong Docker stack | Use `docker-compose.otel-spm.yml`, not `docker-compose.otel.yml` |
| Monitor “No data” but Search works | **Span Kind = Consumer** | Set Monitor → **Span Kind → Server** |
| Sensitive data in Jaeger | Bodies in attributes | Disable body logging; review `messages` attribute exposure |
| `gen_ai.system` shows `openai` for Bedrock | Stale provider guess | Fixed in gateway: provider resolved from ARN/`get_llm_provider`; restart app after upgrade |
| No token attributes on span | Response missing `usage` | Bedrock responses now map Converse usage; verify provider returns `usage` |
| No prompt/completion in Jaeger | `TRACING_CAPTURE_IO=false` | Set `TRACING_CAPTURE_IO=true` (default for OTEL) |
| Jaeger **Monitor** tab empty | SPM needs Prometheus | Use `docker-compose.otel-spm.yml` (Option D), not plain Jaeger |
| Span missing `observability.schema_version=3` | Old code still running | Restart app; reinstall editable package if needed |

**Debug workflow**

1. Set `OTEL_EXPORTER=console` and confirm spans in terminal output.
2. Switch to `otlp_grpc` with `docker-compose.otel-spm.yml`.
3. Inspect collector logs: `docker logs goml-otel-collector`.

---

## Related files

| Path | Description |
|------|-------------|
| [`providers/otel/tracer.py`](providers/otel/tracer.py) | OTel TracerProvider |
| [`providers/otel/exporter.py`](providers/otel/exporter.py) | Exporter selection |
| [`config.py`](config.py) | Env parsing |
| [`hooks.py`](hooks.py) | Span creation on completion |
| [`SETUP.md`](SETUP.md) | All providers (OTEL, Langfuse, goML) |
| [`model_gateway/docker/docker-compose.otel-spm.yml`](../docker/docker-compose.otel-spm.yml) | **Recommended** — Search + Monitor |
| [`model_gateway/docker/README.md`](../docker/README.md) | Docker quick reference |
| [`model_gateway/docker/scripts/verify-jaeger-monitor.ps1`](../docker/scripts/verify-jaeger-monitor.ps1) | Monitor tab diagnostic |
| [`requirements.txt`](../../requirements.txt) | Python OTEL packages |

---

## Quick reference card

```bash
# Terminal 1 — Jaeger Search + Monitor
docker compose -f model_gateway/docker/docker-compose.otel-spm.yml up -d
docker ps --filter "name=goml-"   # all three containers should be Up

# Terminal 2 — your app
pip install -r requirements.txt -r requirements.txt
# .env: OBSERVABILITY_ENABLED=true, TRACING_PROVIDER=otel,
#      OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python test_aim_model_gateway.py --providers bedrock

# Browser — http://localhost:16686
#   Search:  Service goml-gateway → Operation model_gateway.completion → Find Traces
#   Monitor: Service goml-gateway, Span Kind = Server (NOT Consumer)
```
