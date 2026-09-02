"""
RAG (Retrieval-Augmented Generation) Module

Strategies are imported lazily and only if present so subset packages boot.
"""

from app.core.pipelines.rag.base import (
    RAGStrategy,
    RAGConfig,
    RAGResponse,
    RAGType,
    RetrievedDocument,
    RetrievalContext,
    SourceDocument,
)


def _lazy_import_strategies():
    """Lazy import of installed strategies to trigger registration."""
    from app.core.pipelines.rag.strategies import load_available_strategies

    return load_available_strategies()


__all__ = [
    "RAGStrategy",
    "RAGConfig",
    "RAGResponse",
    "RAGType",
    "RetrievedDocument",
    "RetrievalContext",
    "SourceDocument",
]
