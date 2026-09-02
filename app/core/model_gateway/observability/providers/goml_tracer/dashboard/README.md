# goML Tracer Dashboard API

FastAPI server exposing goML SQLite traces for the React UI.

## Run

```bash
pip install -r requirements.txt
set GOML_TRACER_DB_PATH=./data/goml_tracer.db
python -m model_gateway.observability.providers.goml_tracer.dashboard
```

API: http://127.0.0.1:9090/api/health

## Environment

| Variable | Default |
|----------|---------|
| `GOML_TRACER_DB_PATH` | `./data/goml_tracer.db` |
| `GOML_DASHBOARD_HOST` | `127.0.0.1` |
| `GOML_DASHBOARD_PORT` | `9090` |
| `GOML_DASHBOARD_API_KEY` | (optional) |
| `GOML_DASHBOARD_CORS_ORIGINS` | `http://localhost:5173` |
| `GOML_DASHBOARD_SERVE_UI` | `false` — set `true` to serve `ui/goml-tracer-dashboard/dist` |

## Endpoints

- `GET /api/health`
- `GET /api/stats`
- `GET /api/traces?limit=&offset=`
- `GET /api/traces/{trace_id}`
- `GET /api/traces/{trace_id}/spans`
- `GET /api/errors?limit=`
