"""Structured logging and request ID support"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

# Context var for request ID so logs can include it without passing through every call
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        rid = getattr(record, "request_id", None) or request_id_ctx.get()
        if rid:
            log_obj["request_id"] = rid
        return json.dumps(log_obj)


class RequestIDFilter(logging.Filter):
    """Add request_id to log record from context."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class EventLogger:
    """
    Thin stdlib logger wrapper that accepts both classic and event-style calls:

    - logger.info("hello %s", name)
    - logger.info("job_created", job_id=..., url=...)
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _format_event(self, event: Any, kwargs: dict[str, Any]) -> str:
        if not kwargs:
            return str(event)
        extras = " ".join(f"{key}={value!r}" for key, value in kwargs.items())
        return f"{event} {extras}"

    def _log(
        self,
        level: int,
        event: Any,
        *args: Any,
        exc_info: Any = None,
        **kwargs: Any,
    ) -> None:
        if kwargs:
            self._logger.log(level, self._format_event(event, kwargs), exc_info=exc_info)
            return
        if args:
            self._logger.log(level, event, *args, exc_info=exc_info)
            return
        self._logger.log(level, event, exc_info=exc_info)

    def debug(self, event: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, event, *args, **kwargs)

    def info(self, event: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, event, *args, **kwargs)

    def warning(self, event: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, event, *args, **kwargs)

    def error(self, event: Any, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, event, *args, **kwargs)

    def exception(self, event: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("exc_info", None)
        self._log(logging.ERROR, event, *args, exc_info=True, **kwargs)

    def bind(self, **_kwargs: Any) -> EventLogger:
        """Compatibility no-op for callers migrating from structlog."""
        return self


def get_logger(name: str) -> EventLogger:
    """Return an application logger (event-kwargs compatible)."""
    return EventLogger(logging.getLogger(name))


def setup_logging(log_level: str = "INFO", log_format: str = "text") -> None:
    """Configure root logger with level and format (text or json)."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers to avoid duplicate logs
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)

    if log_format == "json":
        stream_handler.setFormatter(JSONFormatter())
    else:
        stream_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(stream_handler)
    root.addFilter(RequestIDFilter())

    # Reduce noise from libraries
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


configure_logging = setup_logging
