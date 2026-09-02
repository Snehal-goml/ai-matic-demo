"""
Vector Database Adapters

Adapters are imported lazily and only if installed so subset ZIPs still boot.
"""

from __future__ import annotations

import importlib
import logging
from typing import List

from app.adapters.vector_store.base import (
    VectorStoreAdapter,
    VectorStoreConfig,
    SearchResult,
    Document,
    DistanceMetric,
)

logger = logging.getLogger(__name__)

_ADAPTER_MODULES = (
    "qdrant",
    "milvus",
    "pgvector",
    "opensearch",
    "aws_opensearch",
    "faiss",
    "neo4j",
)


def _lazy_import_adapters() -> List[str]:
    """Lazy import of installed adapters to trigger registration."""
    available: List[str] = []
    for name in _ADAPTER_MODULES:
        try:
            importlib.import_module(f"app.adapters.vector_store.{name}")
            available.append(name)
        except ModuleNotFoundError:
            logger.info("Vector store adapter not installed: %s", name)
        except Exception as exc:
            logger.warning("Failed to import vector store adapter %s: %s", name, exc)
    return available


__all__ = [
    "VectorStoreAdapter",
    "VectorStoreConfig",
    "SearchResult",
    "Document",
    "DistanceMetric",
]
