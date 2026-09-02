# model_gateway Observability

LiteLLM-style observability for the AI Matic Model Gateway. Enabled automatically on every `completion()` / `acompletion()` call when configured.

**Setup guides:**

- **OpenTelemetry (Docker + integration):** [`OPENTELEMETRY.md`](OPENTELEMETRY.md)
- **Langfuse (Cloud + AWS):** [`LANGFUSE.md`](LANGFUSE.md)
- **goML Tracer (SQLite + dashboard):** [`GOML_TRACER.md`](GOML_TRACER.md)
- **Docker stacks (Jaeger, Langfuse):** [`../docker/README.md`](../docker/README.md)
- **All providers:** [`SETUP.md`](SETUP.md)

## Providers (`TRACING_PROVIDER`)

| Value | Description |
|-------|-------------|
| `otel` | OpenTelemetry OTLP traces (Grafana/Jaeger/Tempo) |
| `langfuse` | Langfuse LLM traces and generations |
| `goml_tracer` | Self-hosted SQLite tracer with query API |
| `noop` | No tracing (default when disabled) |

## Quick start

```bash
pip install -r requirements.txt
```

```env
OBSERVABILITY_ENABLED=true
TRACING_ENABLED=true
TRACING_PROVIDER=goml_tracer
GOML_TRACER_DB_PATH=./data/goml_tracer.db
REQUEST_LOGGING_ENABLED=true
PII_REDACTION_ENABLED=true
LOG_BODIES=false
```

```python
from model_gateway.aim_main import completion

resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "hello"}],
    custom_llm_provider="openai",
)
```

## Query goML traces (Python API)

```python
from model_gateway.observability import init
from model_gateway.observability.config import ObservabilityConfig
from model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api

init(ObservabilityConfig.from_env())
api = get_goml_query_api(ObservabilityConfig.from_env())
print(api.list_traces())
print(api.stats())
```

## Reference implementations

- OpenTelemetry: `litellm/integrations/opentelemetry.py`
- Langfuse: `litellm/integrations/langfuse/`
- Docs/tests: `Dump/docs/my-website/docs/observability/`, `Dump/tests/test_litellm/integrations/`

## Module map

- `hooks.py` — wraps completion lifecycle
- `manager.py` — selects active tracer
- `logger/` — structured JSON logs + PII redaction
- `metrics/` — in-process counters
- `providers/` — otel, langfuse, goml_tracer
