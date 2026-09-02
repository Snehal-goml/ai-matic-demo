from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.model_gateway.observability.providers.goml_tracer.storage.sqlite import SpanRecord


class SpanOut(BaseModel):
    id: str
    trace_id: str
    parent_id: Optional[str] = None
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost: Optional[float] = None


class TraceSummaryOut(BaseModel):
    trace_id: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    span_count: int = 0
    error_count: int = 0


class TraceDetailOut(BaseModel):
    trace: TraceSummaryOut
    spans: List[SpanOut]


class HealthOut(BaseModel):
    status: str
    database: str
    db_path: str
    schema_version: Optional[str] = None


class StatsSummaryOut(BaseModel):
    traces: Optional[int] = None
    spans: Optional[int] = None
    avg_duration_ms: Optional[float] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost: Optional[float] = None
    errors: Optional[int] = None


class ProviderModelStatsOut(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    count: int = 0
    avg_ms: Optional[float] = None
    tin: Optional[int] = None
    tout: Optional[int] = None


class StatsOut(BaseModel):
    summary: StatsSummaryOut
    by_provider_model: List[ProviderModelStatsOut] = Field(default_factory=list)


def span_to_out(record: SpanRecord) -> SpanOut:
    return SpanOut(
        id=record.id,
        trace_id=record.trace_id,
        parent_id=record.parent_id,
        name=record.name,
        start_time=record.start_time,
        end_time=record.end_time,
        duration_ms=record.duration_ms,
        status=record.status,
        error_message=record.error_message,
        metadata=record.metadata or {},
        provider=record.provider,
        model=record.model,
        tokens_input=record.tokens_input,
        tokens_output=record.tokens_output,
        cost=record.cost,
    )


def trace_row_to_out(row: Dict[str, Any]) -> TraceSummaryOut:
    return TraceSummaryOut(
        trace_id=str(row["trace_id"]),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        span_count=int(row.get("span_count") or 0),
        error_count=int(row.get("error_count") or 0),
    )


def stats_to_out(data: Dict[str, Any]) -> StatsOut:
    summary_raw = data.get("summary") or {}
    by_raw = data.get("by_provider_model") or []
    return StatsOut(
        summary=StatsSummaryOut(
            traces=summary_raw.get("traces"),
            spans=summary_raw.get("spans"),
            avg_duration_ms=summary_raw.get("avg_duration_ms"),
            tokens_input=summary_raw.get("tokens_input"),
            tokens_output=summary_raw.get("tokens_output"),
            cost=summary_raw.get("cost"),
            errors=summary_raw.get("errors"),
        ),
        by_provider_model=[
            ProviderModelStatsOut(
                provider=r.get("provider"),
                model=r.get("model"),
                count=int(r.get("count") or 0),
                avg_ms=r.get("avg_ms"),
                tin=r.get("tin"),
                tout=r.get("tout"),
            )
            for r in by_raw
        ],
    )
