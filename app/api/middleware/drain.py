"""Graceful shutdown drain middleware."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class DrainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not hasattr(request.app.state, "draining"):
            return await call_next(request)
        if request.app.state.draining:
            return JSONResponse(
                status_code=503,
                content={"detail": "Server is shutting down"},
                headers={"Retry-After": "30"},
            )
        request.app.state.request_count += 1
        try:
            return await call_next(request)
        finally:
            request.app.state.request_count -= 1
