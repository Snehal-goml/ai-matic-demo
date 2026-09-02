from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StandardCallEvent:
    call_type: str
    model: str
    provider: str
    messages: List[Dict[str, Any]]
    stream: bool = False
    user: Optional[str] = None
    correlation_id: Optional[str] = None

    resolved_model: Optional[str] = None
    resolved_provider: Optional[str] = None

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    latency_ms: Optional[float] = None

    success: bool = False
    error: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0

    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost: Optional[float] = None

    request_body: Optional[Dict[str, Any]] = None
    response_summary: Optional[Dict[str, Any]] = None

    def finish_success(self, response: Any) -> None:
        from app.core.model_gateway.observability.llm_attributes import extract_usage_from_response

        self.success = True
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000.0
        inp, out, _total = extract_usage_from_response(response)
        self.tokens_input = inp
        self.tokens_output = out
        self.response_summary = _summarize_response(response)

    def finish_failure(self, exc: Exception) -> None:
        self.success = False
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000.0
        self.error = str(exc)
        self.error_type = type(exc).__name__

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "call_type": self.call_type,
            "model": self.resolved_model or self.model,
            "provider": self.resolved_provider or self.provider,
            "stream": self.stream,
            "user": self.user,
            "correlation_id": self.correlation_id,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
            "error_type": self.error_type,
            "retry_count": self.retry_count,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "cost": self.cost,
        }


def _summarize_response(response: Any) -> Dict[str, Any]:
    from app.core.model_gateway.observability.llm_attributes import extract_assistant_text

    if response is None:
        return {}
    if isinstance(response, dict):
        summary: Dict[str, Any] = {
            "id": response.get("id"),
            "model": response.get("model"),
            "object": response.get("object"),
        }
        text = extract_assistant_text(response)
        if text is not None:
            summary["content"] = text[:500] if len(text) > 500 else text
        usage = response.get("usage")
        if usage:
            summary["usage"] = usage
        return summary
    if hasattr(response, "model_dump"):
        try:
            data = response.model_dump()
            summary = {
                "id": data.get("id"),
                "model": data.get("model"),
                "object": data.get("object"),
            }
            text = extract_assistant_text(response)
            if text is not None:
                summary["content"] = text[:500] if len(text) > 500 else text
            if data.get("usage"):
                summary["usage"] = data.get("usage")
            return summary
        except Exception:  # noqa: BLE001
            pass
    if hasattr(response, "id"):
        summary = {"id": getattr(response, "id", None), "model": getattr(response, "model", None)}
        text = extract_assistant_text(response)
        if text is not None:
            summary["content"] = text[:500] if len(text) > 500 else text
        return summary
    return {"type": type(response).__name__}


def build_request_body(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    stream: bool,
    optional_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
    if optional_params:
        body.update({k: v for k, v in optional_params.items() if k not in body})
    return body
