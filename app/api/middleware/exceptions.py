"""Shared exception-handler registration."""

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def add_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
