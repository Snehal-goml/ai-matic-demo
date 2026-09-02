# goML_tracer (custom)



Self-hosted distributed tracing with SQLite storage, a Python query API, and an optional React dashboard.



**Full setup guide:** [`../../GOML_TRACER.md`](../../GOML_TRACER.md)



## Quick start



```env

TRACING_PROVIDER=goml_tracer

GOML_TRACER_DB_PATH=./data/goml_tracer.db

GOML_TRACER_RETENTION_DAYS=30

GOML_TRACER_SAMPLING_RATE=1.0

```



```bash

python -m model_gateway.observability.providers.goml_tracer.dashboard

cd ui/goml-tracer-dashboard && npm run dev

```



## Submodules



- `engine/` — spans, context propagation

- `storage/` — SQLite persistence

- `metrics/` — aggregations

- `query/` — `list_traces`, `get_span_tree`, `stats`, `recent_errors`

- `dashboard/` — FastAPI HTTP API for the React UI

- `exporters/` — optional OTLP replay



## See also



- [`dashboard/README.md`](dashboard/README.md) — API endpoints and env vars

- [`ui/goml-tracer-dashboard/README.md`](../../../../ui/goml-tracer-dashboard/README.md) — React UI

