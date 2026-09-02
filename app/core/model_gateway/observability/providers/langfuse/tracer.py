from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.context import get_correlation_id
from app.core.model_gateway.observability.interfaces import Span, TracerProvider
from app.core.model_gateway.observability.logger.redact import redact_pii
from app.core.model_gateway.observability.providers.langfuse.client import build_langfuse_client
from app.core.model_gateway.observability.providers.langfuse.scope import merge_langfuse_metadata


def _usage_details_from_attrs(attrs: Dict[str, Any]) -> Optional[Dict[str, int]]:
    inp = attrs.get("gen_ai.usage.input_tokens") or attrs.get("tokens_input")
    out = attrs.get("gen_ai.usage.output_tokens") or attrs.get("tokens_output")
    details: Dict[str, int] = {}
    if inp is not None:
        try:
            details["input"] = int(inp)
        except (TypeError, ValueError):
            pass
    if out is not None:
        try:
            details["output"] = int(out)
        except (TypeError, ValueError):
            pass
    return details or None


class LangfuseSpanAdapter:
    """Wraps a Langfuse SDK v3+ generation observation (replaces legacy trace + generation API)."""

    def __init__(
        self,
        *,
        observation: Any,
        config: ObservabilityConfig,
    ) -> None:
        self._observation = observation
        self._config = config
        self._attrs: Dict[str, Any] = {}
        self._output: Optional[Any] = None
        self._ended = False

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value

    def record_error(self, err: Exception) -> None:
        self._attrs["error"] = str(err)
        self._attrs["error.type"] = type(err).__name__
        if self._ended:
            return
        try:
            self._observation.update(level="ERROR", status_message=str(err))
            self._observation.end()
            self._ended = True
        except Exception:  # noqa: BLE001
            pass

    def add_event(self, name: str, attributes: Optional[dict[str, Any]] = None) -> None:
        self._attrs.setdefault("events", []).append({"name": name, **(attributes or {})})

    def end(self) -> None:
        if self._ended:
            return
        try:
            output = self._output
            if self._config.pii_redaction_enabled and output is not None:
                output = redact_pii(output, fields=self._config.pii_redaction_fields)
            self._observation.update(
                output=output,
                metadata=self._attrs,
                usage_details=_usage_details_from_attrs(self._attrs),
            )
            self._observation.end()
            self._ended = True
        except Exception:  # noqa: BLE001
            pass

    def set_io(self, *, input_data: Any, output_data: Any) -> None:
        if self._config.pii_redaction_enabled:
            input_data = redact_pii(input_data, fields=self._config.pii_redaction_fields)
            output_data = redact_pii(output_data, fields=self._config.pii_redaction_fields)
        self._output = output_data
        try:
            self._observation.update(input=input_data, output=output_data)
        except Exception:  # noqa: BLE001
            pass


class LangfuseTracer(TracerProvider):
    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._client = build_langfuse_client(config)

    def start_span(
        self,
        name: str,
        *,
        parent: Optional[Span] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> Span:
        attrs = dict(attributes or {})
        model = attrs.get("model") or attrs.get("gen_ai.request.model")
        provider = attrs.get("provider") or attrs.get("gen_ai.system")
        messages = attrs.pop("messages", None)
        if messages is None:
            messages = attrs.get("gen_ai.prompt")

        cid = get_correlation_id()
        trace_id = self._client.create_trace_id(seed=cid) if cid else self._client.create_trace_id()

        metadata = merge_langfuse_metadata(
            self._config,
            {
                "correlation_id": cid,
                "provider": provider,
                **{k: v for k, v in attrs.items() if k not in ("gen_ai.prompt",)},
            },
        )

        observation = self._client.start_observation(
            trace_context={"trace_id": trace_id},
            name=name,
            as_type="generation",
            model=str(model) if model else "unknown",
            input=messages,
            metadata=metadata,
        )
        return LangfuseSpanAdapter(observation=observation, config=self._config)

    def shutdown(self) -> None:
        try:
            self._client.flush()
        except Exception:  # noqa: BLE001
            pass
