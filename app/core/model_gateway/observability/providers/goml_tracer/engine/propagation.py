from __future__ import annotations

from typing import Dict, Optional

TRACEPARENT_HEADER = "traceparent"
CORRELATION_HEADER = "x-correlation-id"


def inject_headers(
    *,
    trace_id: str,
    span_id: str,
    correlation_id: Optional[str] = None,
) -> Dict[str, str]:
    """W3C-inspired trace context (simplified for in-process / future HTTP)."""
    headers: Dict[str, str] = {
        TRACEPARENT_HEADER: f"00-{trace_id.replace('-', '')[:32].ljust(32, '0')}-{span_id.replace('-', '')[:16].ljust(16, '0')}-01",
    }
    if correlation_id:
        headers[CORRELATION_HEADER] = correlation_id
    return headers


def parse_traceparent(value: str) -> Optional[str]:
    parts = value.split("-")
    if len(parts) >= 2:
        return parts[1]
    return None
