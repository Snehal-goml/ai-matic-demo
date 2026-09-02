"""
Document Chunking Strategies

This module provides various chunking strategies for splitting documents.
"""

from app.core.pipelines.rag.ingestion.chunkers.base import ChunkingStrategy, Chunk
from app.core.pipelines.rag.ingestion.chunkers.fixed import FixedSizeChunker
from app.core.pipelines.rag.ingestion.chunkers.semantic import SemanticChunker
from app.core.pipelines.rag.ingestion.chunkers.recursive import RecursiveChunker

__all__ = [
    "ChunkingStrategy",
    "Chunk",
    "FixedSizeChunker",
    "SemanticChunker",
    "RecursiveChunker",
]

