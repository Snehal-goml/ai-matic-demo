from __future__ import annotations

import os
import sqlite3
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.providers.goml_tracer.dashboard.serializers import (
    HealthOut,
    SpanOut,
    StatsOut,
    TraceDetailOut,
    TraceSummaryOut,
    span_to_out,
    stats_to_out,
    trace_row_to_out,
)
from app.core.model_gateway.observability.providers.goml_tracer.query.api import GoMLQueryAPI
from app.core.model_gateway.observability.providers.goml_tracer.storage.migrations import SCHEMA_VERSION
from app.core.model_gateway.observability.providers.goml_tracer.tracer import get_goml_query_api

router = APIRouter(prefix="/api")


def _get_config(request: Request) -> ObservabilityConfig:
    return request.app.state.goml_config


def _get_api(request: Request) -> GoMLQueryAPI:
    return request.app.state.goml_api


def _verify_api_key(request: Request) -> None:
    expected = getattr(request.app.state, "dashboard_api_key", None)
    if not expected:
        return
    provided = request.headers.get("X-API-Key")
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@router.get("/health", response_model=HealthOut, dependencies=[Depends(_verify_api_key)])
def health(request: Request) -> HealthOut:
    cfg: ObservabilityConfig = _get_config(request)
    db_path = cfg.goml_tracer_db_path
    status = "healthy"
    database = "ok"
    schema_version: str | None = str(SCHEMA_VERSION)
    try:
        if not os.path.isfile(db_path):
            database = "missing"
            status = "degraded"
            schema_version = None
        else:
            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key = ?", ("version",)
                ).fetchone()
                if row:
                    schema_version = str(row[0])
            finally:
                conn.close()
    except sqlite3.Error:
        database = "error"
        status = "unhealthy"
    return HealthOut(
        status=status,
        database=database,
        db_path=os.path.abspath(db_path),
        schema_version=schema_version,
    )


@router.get("/stats", response_model=StatsOut, dependencies=[Depends(_verify_api_key)])
def stats(request: Request) -> StatsOut:
    api = _get_api(request)
    return stats_to_out(api.stats())


@router.get("/traces", response_model=List[TraceSummaryOut], dependencies=[Depends(_verify_api_key)])
def list_traces(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[TraceSummaryOut]:
    api = _get_api(request)
    rows = api.list_traces(limit=limit, offset=offset)
    return [trace_row_to_out(r) for r in rows]


@router.get(
    "/traces/{trace_id}",
    response_model=TraceDetailOut,
    dependencies=[Depends(_verify_api_key)],
)
def get_trace(trace_id: str, request: Request) -> TraceDetailOut:
    api = _get_api(request)
    spans = api.get_span_tree(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")
    traces = api.list_traces(limit=500, offset=0)
    summary = next((trace_row_to_out(t) for t in traces if t["trace_id"] == trace_id), None)
    if summary is None:
        root = min(spans, key=lambda s: s.start_time)
        summary = TraceSummaryOut(
            trace_id=trace_id,
            start_time=root.start_time,
            end_time=max((s.end_time or s.start_time) for s in spans),
            span_count=len(spans),
            error_count=sum(1 for s in spans if s.status != "ok"),
        )
    return TraceDetailOut(
        trace=summary,
        spans=[span_to_out(s) for s in spans],
    )


@router.get(
    "/traces/{trace_id}/spans",
    response_model=List[SpanOut],
    dependencies=[Depends(_verify_api_key)],
)
def get_trace_spans(trace_id: str, request: Request) -> List[SpanOut]:
    api = _get_api(request)
    spans = api.get_span_tree(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")
    return [span_to_out(s) for s in spans]


@router.get("/errors", response_model=List[SpanOut], dependencies=[Depends(_verify_api_key)])
def recent_errors(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
) -> List[SpanOut]:
    api = _get_api(request)
    return [span_to_out(s) for s in api.recent_errors(limit=limit)]
