"""
Observability and tracing for model_gateway (LiteLLM-parity callbacks).

Configure via environment variables; see model_gateway/observability/README.md.
"""

from __future__ import annotations

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.manager import ObservabilityManager, get_manager, init, reset_manager

__all__ = [
    "ObservabilityConfig",
    "ObservabilityManager",
    "get_manager",
    "init",
    "reset_manager",
]
