from __future__ import annotations

from typing import Any, Optional

from app.core.model_gateway.observability.config import ObservabilityConfig


def build_langfuse_client(config: ObservabilityConfig) -> Any:
    try:
        from langfuse import Langfuse
    except ImportError as e:
        raise ImportError(
            "langfuse package is required for TRACING_PROVIDER=langfuse. "
            "Install with: pip install -r requirements.txt"
        ) from e

    if not config.langfuse_public_key or not config.langfuse_secret_key:
        raise ValueError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")

    kwargs = {
        "public_key": config.langfuse_public_key,
        "secret_key": config.langfuse_secret_key,
    }
    if config.langfuse_host:
        kwargs["host"] = config.langfuse_host
    if config.langfuse_environment:
        kwargs["environment"] = config.langfuse_environment
    return Langfuse(**kwargs)
