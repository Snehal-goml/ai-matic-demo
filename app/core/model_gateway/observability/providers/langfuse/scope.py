from __future__ import annotations

from typing import Any, Dict, List

from app.core.model_gateway.observability.config import ObservabilityConfig


def langfuse_scope_metadata(config: ObservabilityConfig) -> Dict[str, str]:
    """Trace/generation metadata for project and organization (Langfuse UI filtering)."""
    meta: Dict[str, str] = {}
    if config.langfuse_project_name:
        meta["project_name"] = config.langfuse_project_name
    if config.langfuse_organization_name:
        meta["organization_name"] = config.langfuse_organization_name
    return meta


def langfuse_scope_tags(config: ObservabilityConfig) -> List[str]:
    """Tags for Langfuse trace filtering (when used with propagate_attributes)."""
    tags: List[str] = []
    if config.langfuse_project_name:
        tags.append(f"project:{config.langfuse_project_name}")
    if config.langfuse_organization_name:
        tags.append(f"organization:{config.langfuse_organization_name}")
    return tags


def merge_langfuse_metadata(
    config: ObservabilityConfig,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(metadata)
    for key, value in langfuse_scope_metadata(config).items():
        merged.setdefault(key, value)
    return merged
