# Langfuse setup and integration (model_gateway)

This guide explains how to enable **Langfuse** tracing for the AI Matic Model Gateway, connect to **Langfuse Cloud** or a **self-hosted** instance, view prompts and completions in the Langfuse UI, and deploy on **AWS** (EC2, ECS, Lambda).

---

## Table of contents

1. [How it works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Install Python dependencies](#install-python-dependencies)
4. [Configure model_gateway](#configure-model_gateway)
5. [Langfuse backend: Cloud or Docker](#langfuse-backend-cloud-or-docker)
6. [Run and verify](#run-and-verify)
7. [View results in the Langfuse UI](#view-results-in-the-langfuse-ui)
8. [Integration patterns](#integration-patterns)
9. [Trace and generation data reference](#trace-and-generation-data-reference)
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
LangfuseTracer  ──HTTPS──►  Langfuse Cloud or self-hosted API
   │
   ├── trace (one per completion)
   └── generation (input messages, output summary, model, metadata)
```

- Tracing is **automatic** on every `completion()` call when observability is enabled and `TRACING_PROVIDER=langfuse`.
- Implementation: [`providers/langfuse/tracer.py`](providers/langfuse/tracer.py), [`providers/langfuse/client.py`](providers/langfuse/client.py).
- Each call creates:
  - **Trace** — named `model_gateway.completion` (or `acompletion` via `call_type` metadata).
  - **Generation** — LLM-native record with **input** (messages), **output** (response summary), **model**, and **metadata** (provider, tokens, latency, errors).
- LiteLLM reference (patterns only): `litellm/integrations/langfuse/`, `Dump/docs/my-website/docs/observability/langfuse_integration.md`.

Unlike OpenTelemetry, Langfuse does **not** use OTLP or Jaeger. You use the **Langfuse web UI** for prompts, scores, and evals.

---

## Prerequisites

- Python 3.10+ with `model_gateway` installed (`pip install -r requirements.txt`)
- API keys for your LLM providers (OpenAI, Bedrock, etc.) as usual
- A Langfuse **project** — from [Langfuse Cloud](https://langfuse.com) **or** a local Docker stack (this repo)
- Network access from your app to `LANGFUSE_HOST` (HTTPS for Cloud, `http://localhost:3000` for local Docker)
- **Docker Desktop** (optional) — only if you run Langfuse locally via Docker

---

## Install Python dependencies

Langfuse is an **optional** extra (not in core `requirements.txt`):

```bash
pip install -r requirements.txt
```

| Package | Purpose |
|---------|---------|
| `langfuse` | Langfuse Python SDK (traces, generations, flush) |

---

## Configure model_gateway

Add to your repo root `.env` (or inject via ECS/Lambda/Secrets Manager). **Never commit real API keys.**

### Minimum (Langfuse Cloud — API keys only)

```env
# --- Observability master switch ---
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=langfuse

# --- Langfuse (create keys in Langfuse UI → Settings → API keys) ---
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# --- Recommended logging (works alongside Langfuse) ---
REQUEST_LOGGING_ENABLED=true
RESPONSE_LOGGING_ENABLED=true
LOG_BODIES=false
PII_REDACTION_ENABLED=true
METRICS_ENABLED=true
```

**US region:** use `LANGFUSE_HOST=https://us.cloud.langfuse.com` if your project is on US Cloud.

### Minimum (local Docker — self-hosted UI)

Start Langfuse with Docker (see [Langfuse backend: Cloud or Docker](#langfuse-backend-cloud-or-docker)), then use keys from **http://localhost:3000**:

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=langfuse

LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

PII_REDACTION_ENABLED=true
LOG_BODIES=false
```

Cloud and Docker both use the same `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` variables — only `LANGFUSE_HOST` changes.

Optional labels (filter in Langfuse UI; **API keys** still select the Langfuse project):

```env
LANGFUSE_PROJECT_NAME=goml-model-gateway
LANGFUSE_ORGANIZATION_NAME=my-company
LANGFUSE_ENVIRONMENT=development
```

### All Langfuse-related variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVABILITY_ENABLED` | `false` | Master switch for hooks, logging, metrics |
| `TRACING_ENABLED` | same as above | Enable tracing |
| `TRACING_PROVIDER` | `noop` | Must be `langfuse` for this guide |
| `LANGFUSE_HOST` | Langfuse SDK default | Cloud or self-hosted base URL (no trailing slash) |
| `LANGFUSE_PUBLIC_KEY` | — | Project public key (`pk-lf-...`) — selects which Langfuse **project** receives traces |
| `LANGFUSE_SECRET_KEY` | — | Project secret key (`sk-lf-...`) |
| `LANGFUSE_PROJECT_NAME` | — | Optional label on every trace/generation (`metadata.project_name`) for filtering in the UI |
| `LANGFUSE_ORGANIZATION_NAME` | — | Optional label (`metadata.organization_name`) — does not switch Langfuse org; use for multi-tenant tagging |
| `LANGFUSE_ENVIRONMENT` | — | SDK tracing environment (e.g. `production`, `staging`). Alias: `LANGFUSE_TRACING_ENVIRONMENT` |
| `REQUEST_LOGGING_ENABLED` | `true` | JSON request logs on stderr |
| `RESPONSE_LOGGING_ENABLED` | `true` | JSON response logs on stderr |
| `LOG_BODIES` | `false` | Log full bodies to stderr (off in prod) |
| `PII_REDACTION_ENABLED` | `true` | Redact sensitive fields before Langfuse I/O |
| `METRICS_ENABLED` | `true` | In-process counters (separate from Langfuse UI) |

`TRACING_CAPTURE_IO` applies to **OpenTelemetry** span attributes only. Langfuse always receives **generation input/output** via the Langfuse adapter (still subject to PII redaction).

### Programmatic config (no `.env`)

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig

init(
    ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="langfuse",
        langfuse_host="https://cloud.langfuse.com",
        langfuse_public_key="pk-lf-...",
        langfuse_secret_key="sk-lf-...",
        langfuse_project_name="goml-model-gateway",
        langfuse_organization_name="my-company",
        langfuse_environment="production",
        log_bodies=False,
        pii_redaction_enabled=True,
    )
)
```

Call `init()` **before** the first `completion()` if you use programmatic config.

---

## Langfuse backend: Cloud or Docker

Pick **one** backend. model_gateway uses the same env vars either way; you always need **project API keys** from the Langfuse UI.

| Option | Docker needed? | `LANGFUSE_HOST` | Best for |
|--------|----------------|-----------------|----------|
| **A — Langfuse Cloud** | No | `https://cloud.langfuse.com` (or US) | Fastest start, managed UI |
| **B — Local Docker** | Yes | `http://localhost:3000` | Offline dev, private data, no Cloud account |

```text
Option A (Cloud)                    Option B (Docker)
─────────────────                   ─────────────────
model_gateway ──HTTPS──►            model_gateway ──HTTP──►
  cloud.langfuse.com                  localhost:3000
                                      (Postgres, ClickHouse,
                                       Redis, MinIO via compose)
```

---

### Option A — Langfuse Cloud (API keys only)

No Docker on your machine for the Langfuse server.

1. Sign up at [langfuse.com](https://langfuse.com).
2. Create a **project**.
3. Open **Settings → API keys** → create keys.
4. Set in `.env`:

```env
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

**US region:** `LANGFUSE_HOST=https://us.cloud.langfuse.com`

---

### Option B — Local Docker (self-hosted Langfuse UI)

Run the full Langfuse stack locally with **Docker Compose** (official Langfuse images + Postgres, ClickHouse, Redis, MinIO). Suitable for **development and testing** — not HA production.

#### B1 — Helper script (this repo)

From the repo root:

**Windows:**

```powershell
.\model_gateway\docker\scripts\start-langfuse.ps1
```

**Linux / macOS:**

```bash
chmod +x model_gateway/docker/scripts/start-langfuse.sh
./model_gateway/docker/scripts/start-langfuse.sh
```

The script clones [langfuse/langfuse](https://github.com/langfuse/langfuse) into `model_gateway/docker/langfuse-upstream/` (gitignored) and runs `docker compose up -d`.

| Service | URL |
|---------|-----|
| **Langfuse UI** | http://localhost:3000 |

Wait **2–3 minutes** on first start; check logs:

```bash
docker compose -f model_gateway/docker/langfuse-upstream/docker-compose.yml logs -f langfuse-web
```

Look for **Ready** in the output.

Stop:

```bash
cd model_gateway/docker/langfuse-upstream && docker compose down
```

More detail: [`docker/langfuse/README.md`](../docker/langfuse/README.md)

#### B2 — Manual clone (official compose)

```bash
git clone https://github.com/langfuse/langfuse.git model_gateway/docker/langfuse-upstream
cd model_gateway/docker/langfuse-upstream
```

1. Open `docker-compose.yml` and replace values marked **`# CHANGEME`** with long random secrets (required before any real deployment).
2. Start:

```bash
docker compose up -d
```

3. Open **http://localhost:3000**.

Official guide: [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)

#### After Langfuse is running (Cloud or Docker)

API keys always come from the **Langfuse UI**, not from Docker env alone:

1. Sign up / log in at your `LANGFUSE_HOST` URL.
2. Create a **project**.
3. **Settings → API keys** → create key pair.
4. Configure model_gateway:

```env
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

5. Run a traced `completion()` and flush (see [Run and verify](#run-and-verify)).

#### Docker troubleshooting

| Symptom | Fix |
|---------|-----|
| UI not loading on :3000 | Wait 2–3 min; `docker ps` — web, worker, postgres, clickhouse, redis, minio should be up |
| Port 3000 in use | Stop other services or change published port in upstream `docker-compose.yml` |
| Clone/script fails | Install Git + Docker Desktop; run script from repo root |
| Traces not in local UI | Keys from **this** instance’s UI; `LANGFUSE_HOST=http://localhost:3000`; call `get_manager().shutdown()` |
| Out of disk | Langfuse stores traces locally in Docker volumes — prune or increase disk |

#### Production self-host (not local compose)

For HA production on AWS/Kubernetes, use [Langfuse self-hosting docs](https://langfuse.com/docs/deployment/self-host) — not the single-VM compose alone.

---

### Switching from OpenTelemetry

Only one tracing provider is active at a time:

```env
# Was:
# TRACING_PROVIDER=otel
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Now:
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

See also [`OPENTELEMETRY.md`](OPENTELEMETRY.md) if you need OTLP/Jaeger later.

---

## Run and verify

### Path 1 — With local Docker Langfuse

```bash
# Terminal 1 — Langfuse UI
.\model_gateway\docker\scripts\start-langfuse.ps1
# Open http://localhost:3000 → project → Settings → API keys

# Terminal 2 — model_gateway
pip install -r requirements.txt -r requirements.txt
# .env: TRACING_PROVIDER=langfuse, LANGFUSE_HOST=http://localhost:3000, keys from UI
python test_aim_model_gateway.py --providers bedrock
```

### Path 2 — With Langfuse Cloud

Use Cloud keys in `.env` (`LANGFUSE_HOST=https://cloud.langfuse.com`) — no Docker for Langfuse.

### 1. Install dependencies

```bash
pip install -r requirements.txt -r requirements.txt
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
print(resp.choices[0].message.content if hasattr(resp, "choices") else resp)
```

Or use the smoke test (set `.env` to Langfuse first):

```bash
python test_aim_model_gateway.py --providers openai
```

### 4. Flush before exit (scripts and Lambda)

Langfuse batches events. For short-lived processes:

```python
from model_gateway.observability import get_manager

get_manager().shutdown()  # calls Langfuse client.flush()
```

Long-running servers should flush on **SIGTERM** (ECS task stop, systemd stop) the same way.

### 5. Unit tests (no Langfuse server)

```bash
python -m unittest tests.test_model_gateway_observability -v
```

---

## View results in the Langfuse UI

### Where to open

| Backend | URL |
|---------|-----|
| **Langfuse Cloud (EU)** | https://cloud.langfuse.com |
| **Langfuse Cloud (US)** | https://us.cloud.langfuse.com |
| **Local Docker** (Option B) | http://localhost:3000 |
| **Self-hosted (VM/K8s)** | Your `LANGFUSE_HOST` (e.g. `https://langfuse.internal.example.com`) |

### Step-by-step

1. Confirm `.env` has `TRACING_PROVIDER=langfuse` and valid API keys.
2. Run at least one traced `completion()` (see [Run and verify](#run-and-verify)).
3. Open your Langfuse project → **Tracing** (or **Traces**).
4. Find traces named **`model_gateway.completion`** (or filter by time / metadata).
5. Open a trace → open the **generation** child:
   - **Input** — request messages (redacted if `PII_REDACTION_ENABLED=true`)
   - **Output** — response summary (content snippet, usage when available)
   - **Metadata** — `provider`, `model`, `gen_ai.system`, token fields, `latency_ms`, `correlation_id`, errors

### What you should see for Bedrock

| Field | Expected |
|-------|----------|
| Model | Bedrock model id or ARN |
| Metadata `provider` / `gen_ai.system` | `bedrock` |
| Tokens | `tokens_input`, `tokens_output`, or usage in output summary when the provider returns `usage` |
| Errors | Generation marked ERROR with message on failure |

### If the trace list is empty

- Run `get_manager().shutdown()` before the Python process exits.
- Confirm `LANGFUSE_HOST` matches your project region (EU vs US Cloud).
- Check outbound HTTPS/firewall from your machine or VPC.
- Verify keys in Langfuse UI → Settings → API keys (project must match).
- Temporarily enable debug: ensure no `ImportError` or `ValueError` on startup about missing keys.

---

## Integration patterns

### Sync and async

Both are instrumented automatically:

```python
from model_gateway.aim_main import completion, acompletion

completion(model="...", messages=[...], custom_llm_provider="openai")
await acompletion(model="...", messages=[...], custom_llm_provider="bedrock")
```

### Streaming

`stream=True` is recorded on trace metadata. The generation output is filled when the call completes (full stream duration in `latency_ms`); per-token streaming events are not sent in v1.

### Router / retries

The outer completion is one Langfuse trace/generation. Router retry details appear in metadata (`retry_count` when set via call context); per-attempt child generations are a future enhancement.

### Correlation ID

Each call sets `correlation_id` in trace metadata. Set before calling the gateway from your API layer:

```python
from model_gateway.observability.context import set_correlation_id

set_correlation_id("your-request-id")
```

### Alongside logging and metrics

With `OBSERVABILITY_ENABLED=true` you also get:

- **Structured JSON logs** (stderr) — independent of Langfuse
- **In-process metrics** — `get_manager().metrics.snapshot()`

Langfuse is the **LLM trace UI**; logs/metrics complement it in operations.

### Switching to another provider

```env
TRACING_PROVIDER=otel
# or
TRACING_PROVIDER=goml_tracer
```

See [`SETUP.md`](SETUP.md) and [`OPENTELEMETRY.md`](OPENTELEMETRY.md).

---

## Trace and generation data reference

| Langfuse object | model_gateway mapping |
|-----------------|------------------------|
| Trace name | `model_gateway.completion` |
| Generation name | Same as trace name |
| Generation **model** | Resolved model id / Bedrock ARN |
| Generation **input** | Request `messages` (PII-redacted when enabled) |
| Generation **output** | Response summary (`content`, `usage`, `model`, …) |
| Trace **metadata** | `correlation_id`, `provider`, `model`, `stream`, `call_type`, span attributes |
| Generation **metadata** | `provider` plus attributes set on span end (`tokens_*`, `latency_ms`, `gen_ai.*`, errors) |
| Error | `record_error` → generation ends with ERROR level |

**Bedrock:** Use a Bedrock ARN or `custom_llm_provider=bedrock`. Token counts appear when the response includes `usage` (mapped in `providers/bedrock.py`).

---

## Production notes

1. Store `LANGFUSE_SECRET_KEY` in **AWS Secrets Manager** / **SSM** — not plain text in task definitions.
2. Keep `PII_REDACTION_ENABLED=true` and `LOG_BODIES=false` in production.
3. Call `get_manager().shutdown()` on process/task shutdown so batched events flush.
4. Use **Langfuse Cloud** or a properly HA self-hosted stack — not an unsecured single container on the public internet.
5. Use separate Langfuse **projects** or keys per environment (dev/staging/prod).
6. Langfuse Cloud requires reliable **outbound HTTPS**; self-hosted in VPC uses internal `LANGFUSE_HOST`.

---

## Deploy on AWS (EC2, ECS, Lambda)

Same **model_gateway** code and env vars; Langfuse is reached over **HTTPS** to Cloud or to your internal Langfuse URL.

### Recommended topology

```text
┌──────────────────────────────────────────────────────────────┐
│  EC2 / ECS / Lambda                                           │
│  ┌─────────────────────┐                                     │
│  │  model_gateway       │  HTTPS (443)                       │
│  │  TRACING_PROVIDER=   ├──────────────► Langfuse Cloud      │
│  │  langfuse            │              or self-hosted ALB    │
│  └─────────────────────┘                                     │
└──────────────────────────────────────────────────────────────┘
```

No OTLP collector or Jaeger is required for Langfuse.

### Shared configuration (all compute types)

```bash
pip install -r requirements.txt -r requirements.txt
```

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

LOG_BODIES=false
PII_REDACTION_ENABLED=true
```

Inject keys from **Secrets Manager** (example ECS secret names):

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

**Networking:** allow **outbound HTTPS (443)** to `cloud.langfuse.com`, `us.cloud.langfuse.com`, or your self-hosted Langfuse hostname. No inbound ports needed for tracing.

**Shutdown flush:**

```python
from model_gateway.observability import get_manager

def shutdown_observability() -> None:
    get_manager().shutdown()
```

| Setting | EC2 / ECS | Lambda |
|---------|-----------|--------|
| `LANGFUSE_HOST` | Cloud URL or internal DNS | Same; VPC endpoint optional for private self-host |
| Keys | Secrets Manager / SSM | Lambda secrets extension or env from Secrets Manager |
| Flush | SIGTERM / lifespan | **`finally` in handler** — required |

---

### EC2

1. Launch EC2 in a private subnet with **NAT** for Langfuse Cloud and LLM APIs (or VPC endpoints where available).
2. Install app + `requirements.txt`.
3. Store Langfuse keys in SSM Parameter Store or Secrets Manager; load in systemd unit or app startup.
4. Example `.env` on instance (prefer secrets injection instead of a file):

```env
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
```

5. Run your API/worker; on stop, flush traces:

```python
import signal
from model_gateway.observability import get_manager

def _term(*_):
    get_manager().shutdown()

signal.signal(signal.SIGTERM, _term)
```

6. View traces in Langfuse Cloud (no local UI unless you self-host Langfuse on another host).

**Self-hosted Langfuse on EC2:** deploy Langfuse using [official docs](https://langfuse.com/docs/deployment/self-host) on a separate instance or the same VPC; set `LANGFUSE_HOST=https://langfuse.internal.example.com`.

---

### ECS (Fargate or EC2 launch type)

**Task definition (app container only)** — no sidecar required for Langfuse Cloud:

```json
{
  "containerDefinitions": [
    {
      "name": "model-gateway",
      "image": "<account>.dkr.ecr.<region>.amazonaws.com/goml-gateway:latest",
      "essential": true,
      "environment": [
        { "name": "OBSERVABILITY_ENABLED", "value": "true" },
        { "name": "TRACING_ENABLED", "value": "true" },
        { "name": "TRACING_PROVIDER", "value": "langfuse" },
        { "name": "LANGFUSE_HOST", "value": "https://cloud.langfuse.com" },
        { "name": "PII_REDACTION_ENABLED", "value": "true" },
        { "name": "LOG_BODIES", "value": "false" }
      ],
      "secrets": [
        { "name": "LANGFUSE_PUBLIC_KEY", "valueFrom": "arn:aws:secretsmanager:region:account:secret:langfuse-public" },
        { "name": "LANGFUSE_SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:region:account:secret:langfuse-secret" },
        { "name": "OPENAI_API_KEY", "valueFrom": "arn:aws:secretsmanager:..." }
      ]
    }
  ]
}
```

Register **SIGTERM** in your web framework to call `get_manager().shutdown()` when ECS stops the task.

**Self-hosted Langfuse on ECS:** run Langfuse as its own service (official Helm/compose), put an internal ALB in front, and set `LANGFUSE_HOST` to that ALB DNS from the gateway service security group (allow 443 internal).

---

### Lambda

Langfuse works well with Lambda if you **flush on every invocation** (or use the Langfuse SDK’s async flush patterns for high volume).

```python
import os
from model_gateway.observability import init, get_manager
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.aim_main import completion

init(
    ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="langfuse",
        langfuse_host=os.environ["LANGFUSE_HOST"],
        langfuse_public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        langfuse_secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        pii_redaction_enabled=True,
        log_bodies=False,
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
        get_manager().shutdown()
```

| Topic | Guidance |
|-------|----------|
| VPC | Use NAT gateway for Langfuse Cloud; or internal URL for self-hosted |
| Timeout | Include LLM latency + Langfuse flush in function timeout |
| Memory | 512 MB+ typical; more if large prompts in traces |
| Keys | Lambda environment from Secrets Manager |
| Cold start | First `Langfuse()` client init adds small overhead |

Package `langfuse` in the deployment zip or **container image** alongside `model_gateway`.

---

### AWS deployment checklist

| Step | EC2 | ECS | Lambda |
|------|-----|-----|--------|
| `pip install -r requirements.txt` | Yes | In image | In zip/image |
| `TRACING_PROVIDER=langfuse` | Yes | Task env | Function env |
| Langfuse keys from Secrets Manager | Recommended | Recommended | Recommended |
| Outbound HTTPS to `LANGFUSE_HOST` | Yes | Yes | Yes (NAT if in VPC) |
| `get_manager().shutdown()` on stop | SIGTERM | SIGTERM | **`finally` in handler** |
| PII: `PII_REDACTION_ENABLED=true` | Yes | Yes | Yes |
| View traces | Langfuse Cloud / self-host UI | Same | Same |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| `ImportError: langfuse` | Missing package | `pip install -r requirements.txt` |
| `'Langfuse' object has no attribute 'trace'` | Langfuse SDK v2 API with v3+ installed | Upgrade gateway code / reinstall `langfuse>=3.0.0` (see `providers/langfuse/tracer.py`) |
| `LANGFUSE_PUBLIC_KEY ... must be set` | Keys missing | Set both public and secret keys |
| Empty Langfuse UI | No flush / wrong host | `get_manager().shutdown()`; check EU vs US `LANGFUSE_HOST` |
| Empty Langfuse UI | Network blocked | Allow outbound HTTPS; check proxy |
| `401` / auth errors | Wrong keys or project | Regenerate API keys in Langfuse UI |
| Sensitive data in Langfuse | PII off or log bodies | `PII_REDACTION_ENABLED=true`, `LOG_BODIES=false` |
| Wrong provider in metadata | Old code / no restart | Restart app; Bedrock ARN resolves to `bedrock` |
| No token counts | Response missing `usage` | Bedrock: ensure Converse usage mapped; check generation metadata |
| Traces only in stderr | Wrong provider | `TRACING_PROVIDER=langfuse`, not `otel` or `console` |

**Debug workflow**

1. Confirm env: `TRACING_PROVIDER=langfuse`, keys set, `load_dotenv()` before imports.
2. Run one `completion()` and then `get_manager().shutdown()` in the same script.
3. Open Langfuse → Traces → filter last 15 minutes.
4. If still empty, test keys with a minimal Langfuse SDK script from the same host/VPC.

---

## Related files

| Path | Description |
|------|-------------|
| [`providers/langfuse/tracer.py`](providers/langfuse/tracer.py) | Trace + generation adapter |
| [`providers/langfuse/client.py`](providers/langfuse/client.py) | Langfuse client factory |
| [`config.py`](config.py) | Env parsing (`LANGFUSE_*`) |
| [`hooks.py`](hooks.py) | Completion lifecycle + `set_io` for Langfuse |
| [`SETUP.md`](SETUP.md) | All providers (OTEL, Langfuse, goML) |
| [`OPENTELEMETRY.md`](OPENTELEMETRY.md) | OTLP / Jaeger guide |
| [`requirements.txt`](../../requirements.txt) | `langfuse` package |
| [`docker/langfuse/README.md`](../docker/langfuse/README.md) | Local Docker stack |
| [`docker/scripts/start-langfuse.ps1`](../docker/scripts/start-langfuse.ps1) | Start Langfuse (Windows) |
| [`docker/scripts/start-langfuse.sh`](../docker/scripts/start-langfuse.sh) | Start Langfuse (Linux/macOS) |

---

## Quick reference card

**Option A — Cloud (API keys only):**

```bash
pip install -r requirements.txt -r requirements.txt
# .env: TRACING_PROVIDER=langfuse, LANGFUSE_HOST=https://cloud.langfuse.com, pk/sk from Cloud UI
python test_aim_model_gateway.py --providers bedrock
# UI: https://cloud.langfuse.com → Traces
```

**Option B — Local Docker:**

```bash
# Terminal 1
.\model_gateway\docker\scripts\start-langfuse.ps1
# UI: http://localhost:3000 → create project → API keys

# Terminal 2
pip install -r requirements.txt -r requirements.txt
# .env: LANGFUSE_HOST=http://localhost:3000, keys from local UI
python test_aim_model_gateway.py --providers bedrock
```

**Flush in short scripts:**

```python
from model_gateway.observability import get_manager
get_manager().shutdown()
```
