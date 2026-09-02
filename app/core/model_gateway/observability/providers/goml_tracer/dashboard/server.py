from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.providers.goml_tracer.dashboard.routes import router
from app.core.model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api, reset_goml_singletons


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _ui_dist_path() -> Path:
    return _repo_root() / "ui" / "goml-tracer-dashboard" / "dist"


def _parse_cors_origins(raw: Optional[str]) -> List[str]:
    if not raw:
        return ["http://localhost:5173", "http://127.0.0.1:5173"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(
    *,
    config: Optional[ObservabilityConfig] = None,
    serve_ui: Optional[bool] = None,
) -> FastAPI:
    cfg = config or ObservabilityConfig(
        enabled=True,
        tracing_enabled=True,
        tracing_provider="goml_tracer",
        goml_tracer_db_path=os.getenv("GOML_TRACER_DB_PATH", "./data/goml_tracer.db"),
        goml_tracer_retention_days=int(os.getenv("GOML_TRACER_RETENTION_DAYS", "30")),
        goml_tracer_sampling_rate=float(os.getenv("GOML_TRACER_SAMPLING_RATE", "1.0")),
    )

    reset_goml_singletons()
    app = FastAPI(title="goML Tracer Dashboard", version="1.0.0")
    app.state.goml_config = cfg
    app.state.goml_api = get_goml_query_api(cfg)
    app.state.dashboard_api_key = os.getenv("GOML_DASHBOARD_API_KEY") or None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins(os.getenv("GOML_DASHBOARD_CORS_ORIGINS")),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    should_serve_ui = serve_ui
    if should_serve_ui is None:
        should_serve_ui = os.getenv("GOML_DASHBOARD_SERVE_UI", "").lower() in (
            "1",
            "true",
            "yes",
        )

    dist = _ui_dist_path()
    if should_serve_ui and dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")

    return app
