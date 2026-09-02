from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.model_gateway.observability.providers.goml_tracer.storage.migrations import (
    METADATA_TABLE_SQL,
    SCHEMA_VERSION,
    SPANS_TABLE_SQL,
)


@dataclass
class SpanRecord:
    id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float]
    duration_ms: Optional[float]
    status: str
    error_message: Optional[str]
    metadata: Dict[str, Any]
    provider: Optional[str]
    model: Optional[str]
    tokens_input: Optional[int]
    tokens_output: Optional[int]
    cost: Optional[float]


class SQLiteSpanStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SPANS_TABLE_SQL + METADATA_TABLE_SQL)
                conn.execute(
                    "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                    ("version", str(SCHEMA_VERSION)),
                )
                conn.commit()
            finally:
                conn.close()

    def insert_span(self, record: SpanRecord) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO spans (
                        id, trace_id, parent_id, name, start_time, end_time, duration_ms,
                        status, error_message, metadata_json, provider, model,
                        tokens_input, tokens_output, cost
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.trace_id,
                        record.parent_id,
                        record.name,
                        record.start_time,
                        record.end_time,
                        record.duration_ms,
                        record.status,
                        record.error_message,
                        json.dumps(record.metadata),
                        record.provider,
                        record.model,
                        record.tokens_input,
                        record.tokens_output,
                        record.cost,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def update_span_end(
        self,
        span_id: str,
        *,
        end_time: float,
        duration_ms: float,
        status: str,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        cost: Optional[float] = None,
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                sets = ["end_time = ?", "duration_ms = ?", "status = ?"]
                params: List[Any] = [end_time, duration_ms, status]
                if error_message is not None:
                    sets.append("error_message = ?")
                    params.append(error_message)
                if metadata is not None:
                    sets.append("metadata_json = ?")
                    params.append(json.dumps(metadata))
                if tokens_input is not None:
                    sets.append("tokens_input = ?")
                    params.append(tokens_input)
                if tokens_output is not None:
                    sets.append("tokens_output = ?")
                    params.append(tokens_output)
                if cost is not None:
                    sets.append("cost = ?")
                    params.append(cost)
                params.append(span_id)
                conn.execute(
                    f"UPDATE spans SET {', '.join(sets)} WHERE id = ?",
                    params,
                )
                conn.commit()
            finally:
                conn.close()

    def list_traces(self, *, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT trace_id,
                           MIN(start_time) AS start_time,
                           MAX(COALESCE(end_time, start_time)) AS end_time,
                           COUNT(*) AS span_count,
                           SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS error_count
                    FROM spans
                    GROUP BY trace_id
                    ORDER BY start_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_spans_for_trace(self, trace_id: str) -> List[SpanRecord]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_time ASC",
                    (trace_id,),
                ).fetchall()
                return [_row_to_record(r) for r in rows]
            finally:
                conn.close()

    def recent_errors(self, *, limit: int = 50) -> List[SpanRecord]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM spans
                    WHERE status != 'ok'
                    ORDER BY start_time DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
                return [_row_to_record(r) for r in rows]
            finally:
                conn.close()

    def aggregate_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(DISTINCT trace_id) AS traces,
                           COUNT(*) AS spans,
                           AVG(duration_ms) AS avg_duration_ms,
                           SUM(COALESCE(tokens_input, 0)) AS tokens_input,
                           SUM(COALESCE(tokens_output, 0)) AS tokens_output,
                           SUM(COALESCE(cost, 0)) AS cost,
                           SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS errors
                    FROM spans
                    WHERE parent_id IS NULL OR id IN (
                        SELECT id FROM spans WHERE parent_id IS NULL
                    )
                    """
                ).fetchone()
                by_provider = conn.execute(
                    """
                    SELECT provider, model,
                           COUNT(*) AS count,
                           AVG(duration_ms) AS avg_ms,
                           SUM(COALESCE(tokens_input, 0)) AS tin,
                           SUM(COALESCE(tokens_output, 0)) AS tout
                    FROM spans
                    WHERE provider IS NOT NULL
                    GROUP BY provider, model
                    """
                ).fetchall()
                return {
                    "summary": dict(row) if row else {},
                    "by_provider_model": [dict(r) for r in by_provider],
                }
            finally:
                conn.close()

    def apply_retention(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp()
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM spans WHERE start_time < ?", (cutoff,))
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()


def _row_to_record(row: sqlite3.Row) -> SpanRecord:
    meta_raw = row["metadata_json"]
    metadata: Dict[str, Any] = {}
    if meta_raw:
        try:
            metadata = json.loads(meta_raw)
        except json.JSONDecodeError:
            metadata = {}
    return SpanRecord(
        id=row["id"],
        trace_id=row["trace_id"],
        parent_id=row["parent_id"],
        name=row["name"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        duration_ms=row["duration_ms"],
        status=row["status"],
        error_message=row["error_message"],
        metadata=metadata,
        provider=row["provider"],
        model=row["model"],
        tokens_input=row["tokens_input"],
        tokens_output=row["tokens_output"],
        cost=row["cost"],
    )
