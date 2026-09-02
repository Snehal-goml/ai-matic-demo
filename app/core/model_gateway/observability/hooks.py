from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from app.core.model_gateway.observability.context import (
    clear_call_context,
    ensure_correlation_id,
    get_call_context,
)
from app.core.model_gateway.observability.events import StandardCallEvent, build_request_body
from app.core.model_gateway.observability.interfaces import Span
from app.core.model_gateway.observability.llm_attributes import (
    extract_assistant_text,
    extract_usage_from_response,
    infer_provider_from_model,
    summarize_messages_for_span,
)
from app.core.model_gateway.observability.logger.redact import redact_pii
from app.core.model_gateway.observability.manager import get_manager

T = TypeVar("T")

SPAN_NAME = "model_gateway.completion"
OBSERVABILITY_SCHEMA_VERSION = "3"


def _resolve_provider_model(
    *,
    provider: str,
    model: str,
    resolved_provider: Optional[str] = None,
    resolved_model: Optional[str] = None,
) -> tuple[str, str]:
    prov = resolved_provider or provider
    mdl = resolved_model or model
    inferred = infer_provider_from_model(mdl) or infer_provider_from_model(model)
    if inferred:
        prov = inferred
    return prov, mdl


def _should_capture_io(mgr: Any) -> bool:
    return bool(mgr.config.tracing_capture_io or mgr.config.log_bodies)


def _safe_set(span: Span, key: str, value: Any) -> None:
    """OTLP attributes must be primitives or homogeneous primitive arrays."""
    if value is None:
        return
    if isinstance(value, (str, bool, int, float)):
        span.set_attribute(key, value)
        return
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        span.set_attribute(key, list(value))
        return
    span.set_attribute(key, str(value))


def _span_attributes(event: StandardCallEvent, *, mgr: Any) -> Dict[str, Any]:
    provider, model = _resolve_provider_model(
        provider=event.provider,
        model=event.model,
        resolved_provider=event.resolved_provider,
        resolved_model=event.resolved_model,
    )
    attrs: Dict[str, Any] = {
        "gen_ai.system": provider,
        "gen_ai.request.model": model,
        "provider": provider,
        "model": model,
        "stream": event.stream,
        "call_type": event.call_type,
        "correlation_id": event.correlation_id,
        "observability.schema_version": OBSERVABILITY_SCHEMA_VERSION,
    }
    if event.user:
        attrs["user"] = event.user
    if _should_capture_io(mgr):
        prompt_msgs = event.messages
        if mgr.config.pii_redaction_enabled:
            prompt_msgs = redact_pii(prompt_msgs, fields=mgr.config.pii_redaction_fields)
        attrs["gen_ai.prompt"] = summarize_messages_for_span(prompt_msgs)
    return attrs


def _start_span(mgr: Any, event: StandardCallEvent) -> Span:
    attrs = _span_attributes(event, mgr=mgr)
    span = mgr.tracer.start_span(SPAN_NAME, attributes={})
    for key, value in attrs.items():
        _safe_set(span, key, value)
    return span


def _apply_event_to_span(span: Span, event: StandardCallEvent, *, mgr: Any) -> None:
    provider, model = _resolve_provider_model(
        provider=event.provider,
        model=event.model,
        resolved_provider=event.resolved_provider,
        resolved_model=event.resolved_model,
    )

    _safe_set(span, "gen_ai.system", provider)
    _safe_set(span, "gen_ai.request.model", model)
    _safe_set(span, "provider", provider)
    _safe_set(span, "model", model)

    if event.tokens_input is not None:
        _safe_set(span, "tokens_input", int(event.tokens_input))
        _safe_set(span, "gen_ai.usage.input_tokens", int(event.tokens_input))
        _safe_set(span, "gen_ai.usage.prompt_tokens", int(event.tokens_input))
    if event.tokens_output is not None:
        _safe_set(span, "tokens_output", int(event.tokens_output))
        _safe_set(span, "gen_ai.usage.output_tokens", int(event.tokens_output))
        _safe_set(span, "gen_ai.usage.completion_tokens", int(event.tokens_output))
    if event.tokens_input is not None and event.tokens_output is not None:
        _safe_set(
            span,
            "gen_ai.usage.total_tokens",
            int(event.tokens_input) + int(event.tokens_output),
        )
    if event.cost is not None:
        _safe_set(span, "cost", float(event.cost))
    if event.retry_count:
        _safe_set(span, "retry_count", int(event.retry_count))
    if event.latency_ms is not None:
        _safe_set(span, "latency_ms", float(event.latency_ms))

    if _should_capture_io(mgr):
        prompt_msgs = event.messages
        if mgr.config.pii_redaction_enabled:
            prompt_msgs = redact_pii(prompt_msgs, fields=mgr.config.pii_redaction_fields)
        _safe_set(span, "gen_ai.prompt", summarize_messages_for_span(prompt_msgs))


def _finalize_resolved(
    event: StandardCallEvent,
    result: Any,
    fallback_provider: str,
    fallback_model: str,
) -> None:
    ctx = get_call_context()
    if ctx:
        event.resolved_provider = str(ctx.get("provider") or fallback_provider)
        event.resolved_model = str(ctx.get("model") or fallback_model)
        event.retry_count = int(ctx.get("retry_count") or 0)
        clear_call_context()
    else:
        event.resolved_provider = fallback_provider
        event.resolved_model = fallback_model

    # Model ARN/id wins over a stale router provider guess (e.g. openai).
    inferred = infer_provider_from_model(event.resolved_model) or infer_provider_from_model(
        event.model
    )
    if inferred:
        event.resolved_provider = inferred

    if hasattr(result, "model") and not isinstance(result, dict):
        event.resolved_model = getattr(result, "model", None) or event.resolved_model
    elif isinstance(result, dict) and result.get("model"):
        event.resolved_model = str(result["model"])
        inferred_result = infer_provider_from_model(event.resolved_model)
        if inferred_result:
            event.resolved_provider = inferred_result

    provider, model = _resolve_provider_model(
        provider=event.provider,
        model=event.model,
        resolved_provider=event.resolved_provider,
        resolved_model=event.resolved_model,
    )
    event.resolved_provider = provider
    event.resolved_model = model


def _apply_response_io(span: Span, event: StandardCallEvent, result: Any, *, mgr: Any) -> None:
    if not _should_capture_io(mgr):
        return
    text = extract_assistant_text(result)
    if text is None and event.response_summary:
        text = str(event.response_summary.get("content", ""))
    if text:
        if mgr.config.pii_redaction_enabled:
            text = str(
                redact_pii({"content": text}, fields=mgr.config.pii_redaction_fields).get(
                    "content"
                )
            )
        _safe_set(span, "gen_ai.completion", text[:8000] if len(text) > 8000 else text)


def _apply_usage_fallback(span: Span, result: Any) -> None:
    inp, out, total = extract_usage_from_response(result)
    if inp is not None:
        _safe_set(span, "gen_ai.usage.input_tokens", inp)
        _safe_set(span, "gen_ai.usage.prompt_tokens", inp)
    if out is not None:
        _safe_set(span, "gen_ai.usage.output_tokens", out)
        _safe_set(span, "gen_ai.usage.completion_tokens", out)
    if total is not None:
        _safe_set(span, "gen_ai.usage.total_tokens", total)


def observe_sync(
    fn: Callable[[], T],
    *,
    call_type: str,
    model: str,
    messages: List[Dict[str, Any]],
    provider: str,
    stream: bool = False,
    user: Optional[str] = None,
    optional_params: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    resolved_provider: Optional[str] = None,
    resolved_model: Optional[str] = None,
) -> T:
    mgr = get_manager()
    if not mgr.config.enabled:
        return fn()

    prov, mdl = _resolve_provider_model(
        provider=provider,
        model=model,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
    )

    cid = ensure_correlation_id(correlation_id)
    event = StandardCallEvent(
        call_type=call_type,
        model=model,
        provider=prov,
        messages=messages,
        stream=stream,
        user=user,
        correlation_id=cid,
        resolved_provider=prov,
        resolved_model=mdl,
    )
    body = build_request_body(
        model=model, messages=messages, stream=stream, optional_params=optional_params
    )
    if mgr.config.pii_redaction_enabled:
        body = redact_pii(body, fields=mgr.config.pii_redaction_fields)
    event.request_body = body

    span = _start_span(mgr, event)
    mgr.logger.log_request(event)

    try:
        result = fn()
        if hasattr(result, "__iter__") and stream and not hasattr(result, "model_dump"):
            _finalize_resolved(event, result, prov, mdl)
            event.finish_success(result)
            _apply_event_to_span(span, event, mgr=mgr)
            _apply_usage_fallback(span, result)
            _apply_response_io(span, event, result, mgr=mgr)
            mgr.logger.log_response(event)
            mgr.metrics.record_event(event)
            span.end()
            return result

        _finalize_resolved(event, result, prov, mdl)
        event.finish_success(result)
        _apply_event_to_span(span, event, mgr=mgr)
        _apply_usage_fallback(span, result)
        _apply_response_io(span, event, result, mgr=mgr)
        _maybe_set_langfuse_io(span, event, result)
        mgr.logger.log_response(event)
        mgr.metrics.record_event(event)
        span.end()
        return result
    except Exception as exc:
        _finalize_resolved(event, None, prov, mdl)
        event.finish_failure(exc)
        span.record_error(exc)
        _apply_event_to_span(span, event, mgr=mgr)
        mgr.logger.log_error(event, exc)
        mgr.metrics.record_event(event)
        span.end()
        raise
    finally:
        clear_call_context()


async def observe_async(
    fn: Callable[[], Awaitable[T]],
    *,
    call_type: str,
    model: str,
    messages: List[Dict[str, Any]],
    provider: str,
    stream: bool = False,
    user: Optional[str] = None,
    optional_params: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    resolved_provider: Optional[str] = None,
    resolved_model: Optional[str] = None,
) -> T:
    mgr = get_manager()
    if not mgr.config.enabled:
        return await fn()

    prov, mdl = _resolve_provider_model(
        provider=provider,
        model=model,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
    )

    cid = ensure_correlation_id(correlation_id)
    event = StandardCallEvent(
        call_type=call_type,
        model=model,
        provider=prov,
        messages=messages,
        stream=stream,
        user=user,
        correlation_id=cid,
        resolved_provider=prov,
        resolved_model=mdl,
    )
    body = build_request_body(
        model=model, messages=messages, stream=stream, optional_params=optional_params
    )
    if mgr.config.pii_redaction_enabled:
        body = redact_pii(body, fields=mgr.config.pii_redaction_fields)
    event.request_body = body

    span = _start_span(mgr, event)
    mgr.logger.log_request(event)

    try:
        result = await fn()
        _finalize_resolved(event, result, prov, mdl)
        event.finish_success(result)
        _apply_event_to_span(span, event, mgr=mgr)
        _apply_usage_fallback(span, result)
        _apply_response_io(span, event, result, mgr=mgr)
        _maybe_set_langfuse_io(span, event, result)
        mgr.logger.log_response(event)
        mgr.metrics.record_event(event)
        span.end()
        return result
    except Exception as exc:
        _finalize_resolved(event, None, prov, mdl)
        event.finish_failure(exc)
        span.record_error(exc)
        _apply_event_to_span(span, event, mgr=mgr)
        mgr.logger.log_error(event, exc)
        mgr.metrics.record_event(event)
        span.end()
        raise
    finally:
        clear_call_context()


def _maybe_set_langfuse_io(span: Span, event: StandardCallEvent, result: Any) -> None:
    if hasattr(span, "set_io"):
        span.set_io(  # type: ignore[attr-defined]
            input_data={"messages": event.messages, "model": event.model},
            output_data=event.response_summary,
        )
