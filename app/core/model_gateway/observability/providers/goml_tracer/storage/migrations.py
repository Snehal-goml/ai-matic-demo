SCHEMA_VERSION = 1

SPANS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS spans (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_id TEXT,
    name TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    duration_ms REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT,
    metadata_json TEXT,
    provider TEXT,
    model TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    cost REAL
);
CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_start_time ON spans(start_time);
CREATE INDEX IF NOT EXISTS idx_spans_provider_model ON spans(provider, model);
"""

METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
