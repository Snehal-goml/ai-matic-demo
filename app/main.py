import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
import uvicorn

from app.api.dependencies.rate_limit import limiter
from app.api.endpoints import health
from app.api.endpoints.idp import api as idp_feature
from app.api.endpoints.rag import api as rag_feature
from app.config.settings import (
    get_settings,
    settings,
    SOLUTION_BUNDLES,
    SOLUTION_COMPONENTS,
)
from app.core.feature_contract import FeatureModule
from app.observability.logging_config import configure_logging, request_id_ctx

# Load env and configure logging before creating app
_settings = get_settings()
configure_logging(log_level=_settings.LOG_LEVEL, log_format=_settings.LOG_FORMAT)
logger = logging.getLogger(__name__)

IS_LAMBDA = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

SUPPORTED_EXTRACTOR_TYPES = ("AWS_textract", "goml_custom_extractor")

# The two composed solution bundles for the AI Document Knowledge Assistant.
FEATURES: list[FeatureModule] = [idp_feature.FEATURE, rag_feature.FEATURE]


def _validate_config() -> None:
    """Run each enabled feature's startup validation (IDP + RAG)."""
    for feature in FEATURES:
        if feature.on_startup is not None:
            logger.info("Running startup validation for feature '%s'", feature.slug)
            feature.on_startup()
    if _settings.EXTRACTOR_TYPE not in SUPPORTED_EXTRACTOR_TYPES:
        raise ValueError(
            f"EXTRACTOR_TYPE must be one of {SUPPORTED_EXTRACTOR_TYPES}, "
            f"got: {_settings.EXTRACTOR_TYPE}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init state and validate config. Shutdown: set draining and wait for in-flight requests."""
    _validate_config()
    app.state.request_count = 0
    app.state.draining = False
    yield
    app.state.draining = True
    drain_seconds = get_settings().SHUTDOWN_DRAIN_SECONDS
    deadline = asyncio.get_event_loop().time() + drain_seconds
    while getattr(app.state, "request_count", 0) > 0 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
    logger.info("Shutdown drain complete")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Read or generate X-Request-ID, set on state/response and inject into log context."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)


class DrainMiddleware(BaseHTTPMiddleware):
    """When draining: return 503. Otherwise track in-flight request count."""

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


def _bundle_config() -> dict:
    """Describe the active solution-bundle configuration for /api/config."""
    return {
        "app": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "solution_bundles": SOLUTION_BUNDLES,
        "components": SOLUTION_COMPONENTS,
        "active": {
            "extractor": _settings.EXTRACTOR_TYPE,
            "rag_strategy": _settings.DEFAULT_RAG_TYPE,
            "vector_store": _settings.DEFAULT_VECTOR_STORE,
            "llm_provider": _settings.LLM_PROVIDER,
            "embedding_model": _settings.EMBEDDING_MODEL_ID,
        },
        "features": [
            {
                "slug": f.slug,
                "prefix": f.prefix,
                "tags": list(f.tags),
                "health_checks": sorted(f.health_checks.keys()),
            }
            for f in FEATURES
        ],
    }


def create_app() -> FastAPI:
    """Create the FastAPI app composed of the IDP + RAG bundles; lifespan only when not running in Lambda."""
    app = FastAPI(
        title=settings.APP_TITLE,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        lifespan=lifespan if not IS_LAMBDA else None,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(DrainMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list({o.strip() for o in (settings.CORS_ALLOW_ORIGINS or "*").split(",")}),
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=list({m.strip() for m in (settings.CORS_ALLOW_METHODS or "").split(",") if m.strip()})
        or ["GET", "OPTIONS", "POST", "PUT", "DELETE"],
        allow_headers=list({h.strip() for h in (settings.CORS_ALLOW_HEADERS or "*").split(",")}),
    )

    # Register each enabled feature's readiness checks under /api/health/ready.
    for feature in FEATURES:
        if feature.health_checks:
            health.register_health_checks(feature.slug, feature.health_checks)

    # Shared liveness / readiness probes.
    app.include_router(health.router, prefix="/api/health", tags=["Health"])

    # Compose the two selected bundles: IDP + RAG.
    app.include_router(
        idp_feature.FEATURE.router,
        prefix=idp_feature.FEATURE.prefix,
        tags=idp_feature.FEATURE.tags,
    )
    app.include_router(
        rag_feature.FEATURE.router,
        prefix=rag_feature.FEATURE.prefix,
        tags=rag_feature.FEATURE.tags,
    )

    @app.get("/api/config", tags=["Configuration"])
    async def api_config() -> dict:
        """Report the active selection of solution bundles and nested components."""
        return _bundle_config()

    @app.get("/", tags=["Root"])
    async def root() -> dict:
        """API root with the bundle configuration and helpful links."""
        return {
            "message": "AI Document Knowledge Assistant API (IDP + RAG)",
            "docs": "/docs",
            "redoc": "/redoc",
            "config": "/api/config",
            "features": {f.slug: f.prefix for f in FEATURES},
            "example_ingest": "/api/rag/ingestion/file",
            "example_query": "/api/rag/naive/query",
        }

    return app


app = create_app()

# Expose handler for Lambda
handler = Mangum(app, lifespan="off")
if __name__ == "__main__":
    uvicorn.run('app.main:app', host="0.0.0.0", port=8000, reload=True)