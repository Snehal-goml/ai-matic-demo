from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, Optional

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.events import StandardCallEvent
from app.core.model_gateway.observability.logger.redact import redact_pii


class StructuredLogger:
    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._logger = logging.getLogger("model_gateway.observability")
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
        level = getattr(logging, config.log_level.upper(), logging.INFO)
        self._logger.setLevel(level)

    def _emit(self, payload: Dict[str, Any]) -> None:
        if self._config.pii_redaction_enabled:
            payload = redact_pii(
                payload,
                fields=self._config.pii_redaction_fields,
                enabled=True,
            )
        self._logger.info(json.dumps(payload, default=str))

    def log_request(self, event: StandardCallEvent) -> None:
        if not self._config.request_logging_enabled:
            return
        payload: Dict[str, Any] = {
            "event": "request",
            **event.to_log_dict(),
        }
        if self._config.log_bodies and event.request_body is not None:
            payload["request_body"] = event.request_body
        self._emit(payload)

    def log_response(self, event: StandardCallEvent) -> None:
        if not self._config.response_logging_enabled:
            return
        payload: Dict[str, Any] = {
            "event": "response",
            **event.to_log_dict(),
        }
        if self._config.log_bodies and event.response_summary is not None:
            payload["response"] = event.response_summary
        self._emit(payload)

    def log_error(self, event: StandardCallEvent, exc: Optional[Exception] = None) -> None:
        payload: Dict[str, Any] = {
            "event": "error",
            **event.to_log_dict(),
        }
        if exc is not None:
            payload["exception"] = type(exc).__name__
        self._emit(payload)
