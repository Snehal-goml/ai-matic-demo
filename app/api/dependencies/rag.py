"""
RAG feature dependency injection.

Lives in app/api/dependencies/rag.py so it can coexist with Adapter-owned
auth.py / rate_limit.py / empty package __init__.py.
"""

import logging
from typing import Dict, Any
from fastapi import Depends, HTTPException, Query

from app.config.settings import settings
from app.utils.rag.llm_client import GatewayLLMClient
from app.adapters.vector_store.base import VectorStoreConfig, DistanceMetric
from app.config.rag.registry import VectorStoreRegistry

logger = logging.getLogger(__name__)

# Global instances (initialized on first use)
_llm_client = None
_embedder = None
_vector_store_instances: Dict[str, Any] = {}


def get_llm_client():
    """Get or create the LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = GatewayLLMClient()
    return _llm_client


def get_embedder():
    """Get or create the embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = GatewayLLMClient()
    return _embedder


async def get_vector_store(
    vector_store_type: str = Query(default="qdrant", description="Vector store type")
):
    """
    Get or create a vector store adapter instance.
    
    This dependency manages connection lifecycle for vector stores.
    """
    global _vector_store_instances
    
    if vector_store_type in _vector_store_instances:
        return _vector_store_instances[vector_store_type]
    
    try:
        # Get embedder to determine dimension
        embedder = get_embedder()
        # Build config based on vector store type with correct dimension
        config = _get_vector_store_config(vector_store_type, embedder=embedder)
        
        # Create adapter
        adapter = VectorStoreRegistry.create_adapter(vector_store_type, config)
        
        # Connect
        await adapter.connect()
        
        # Cache instance
        _vector_store_instances[vector_store_type] = adapter
        
        return adapter
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to initialize vector store {vector_store_type}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to connect to vector store: {str(e)}"
        )


def _get_vector_store_config(vector_store_type: str, embedder=None) -> VectorStoreConfig:
    """
    Get configuration for a specific vector store type.
    
    Args:
        vector_store_type: Type of vector store.
        embedder: Optional embedder instance to get dimension from.
    """
    # Get embedding dimension from embedder if available
    vector_dim = 1024  # Default fallback
    if embedder and hasattr(embedder, 'embedding_dimension'):
        vector_dim = embedder.embedding_dimension
        logger.debug(f"Using embedding dimension from embedder: {vector_dim}")
    else:
        logger.warning(f"Could not determine embedding dimension from embedder. Using default: {vector_dim}")
    
    configs = {
        "qdrant": VectorStoreConfig(
            host=getattr(settings, "QDRANT_URL", "localhost"),
            port=getattr(settings, "QDRANT_PORT", 6333),
            api_key=getattr(settings, "QDRANT_API_KEY", None),
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
        ),
        "milvus": VectorStoreConfig(
            host=str(getattr(settings, "MILVUS_URI", None) or getattr(settings, "MILVUS_HOST", "localhost") or "localhost"),
            port=int(getattr(settings, "MILVUS_PORT", 19530) or 19530),
            api_key=getattr(settings, "MILVUS_TOKEN", None),
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "uri": getattr(settings, "MILVUS_URI", None),  # For Milvus Cloud
            }
        ),
        "pgvector": VectorStoreConfig(
            host=getattr(settings, "POSTGRES_SERVER", "localhost"),
            port=getattr(settings, "POSTGRES_PORT", 5432),
            api_key=getattr(settings, "POSTGRES_PASSWORD", None),
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "user": getattr(settings, "POSTGRES_USER", "postgres"),
                "database": getattr(settings, "POSTGRES_DB", "vectors"),
                "schema": getattr(settings, "POSTGRES_SCHEMA", None),
            }
        ),
        "opensearch": VectorStoreConfig(
            host=getattr(settings, "OPENSEARCH_HOST", "localhost"),
            port=getattr(settings, "OPENSEARCH_PORT", 9200),
            api_key=getattr(settings, "OPENSEARCH_PASSWORD", None),
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "user": getattr(settings, "OPENSEARCH_USER", "admin"),
                "use_ssl": getattr(settings, "OPENSEARCH_USE_SSL", True),
            }
        ),
        "faiss": VectorStoreConfig(
            host="local",
            port=0,
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "storage_path": getattr(settings, "FAISS_STORAGE_PATH", "./faiss_data"),
            }
        ),
        "neo4j": VectorStoreConfig(
            host=getattr(settings, "NEO4J_URI", None) or getattr(settings, "NEO4J_HOST", "localhost"),
            port=getattr(settings, "NEO4J_PORT", 7687),
            api_key=getattr(settings, "NEO4J_PASSWORD", None),
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "user": getattr(settings, "NEO4J_USER", "neo4j"),
                "uri": getattr(settings, "NEO4J_URI", None),  # For AuraDB cloud
            }
        ),
        "aws_opensearch": VectorStoreConfig(
            host=getattr(settings, "AWS_OPENSEARCH_ENDPOINT", ""),
            port=443,  # AWS OpenSearch uses HTTPS on port 443
            api_key=None,  # Uses AWS SigV4, not API key
            vector_dim=vector_dim,
            distance_metric=DistanceMetric.COSINE,
            extra_params={
                "aws_region": getattr(settings, "AWS_OPENSEARCH_REGION", "us-east-1"),
                "aws_access_key_id": getattr(settings, "AWS_ACCESS_KEY_ID", None),
                "aws_secret_access_key": getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            }
        ),
    }
    
    if vector_store_type not in configs:
        available = list(configs.keys())
        raise ValueError(f"Unknown vector store: {vector_store_type}. Available: {available}")
    
    return configs[vector_store_type]


async def get_rag_components() -> Dict[str, Any]:
    """
    Get all RAG components needed for query execution.
    
    Note: The vector store adapter is determined by the 'vector_store' field in the request body.
    This dependency provides LLM and embedder instances. The vector store adapter is created
    dynamically based on the request body's vector_store field in the service layer.
    
    Returns a dict with:
    - llm: The LLM client
    - embedder: The embedding client
    """
    llm = get_llm_client()
    embedder = get_embedder()
    
    return {
        "llm": llm,
        "embedder": embedder,
    }
