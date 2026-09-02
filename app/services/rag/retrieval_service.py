"""
RAG Service

Business logic for RAG operations.
Handles strategy creation and execution.
"""

import logging
from typing import Dict, Any, Optional

from app.core.pipelines.rag.base import RAGConfig, RAGResponse
from app.adapters.vector_store.base import VectorStoreAdapter, VectorStoreConfig, DistanceMetric
from app.config.rag.registry import VectorStoreRegistry

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
def _get_strategy_class(rag_type: str):
    """Get strategy class by type with lazy import."""
    logger.debug(f"Resolving RAG strategy class for rag_type='{rag_type}'")
    if rag_type == "naive":
        from app.core.pipelines.rag.strategies.naive import NaiveRAG
        return NaiveRAG
    elif rag_type == "advanced":
        from app.core.pipelines.rag.strategies.advanced import AdvancedRAG
        return AdvancedRAG
    elif rag_type == "hierarchical":
        from app.core.pipelines.rag.strategies.hierarchical import HierarchicalRAG
        return HierarchicalRAG
    elif rag_type == "graph":
        from app.core.pipelines.rag.strategies.graph import GraphRAG
        return GraphRAG
    elif rag_type == "agentic":
        from app.core.pipelines.rag.strategies.agentic import AgenticRAG
        return AgenticRAG
    elif rag_type == "hybrid":
        from app.core.pipelines.rag.strategies.hybrid import HybridRAG
        return HybridRAG
    elif rag_type == "conversational":
        from app.core.pipelines.rag.strategies.conversational import ConversationalRAG
        return ConversationalRAG
    else:
        logger.error(f"Unknown RAG type requested: {rag_type}")
        raise ValueError(f"Unknown RAG type: {rag_type}")


class RAGService:
    """
    Service for executing RAG queries.
    
    Handles strategy selection, configuration, and execution.
    """

    def __init__(
        self,
        llm_client: Any,
        embedder: Any
    ):
        """
        Initialize the RAG service.
        
        Args:
            llm_client: LLM client for generation.
            embedder: Embedding client.
        """
        self.llm = llm_client
        self.embedder = embedder
        self._vector_store_cache: Dict[str, VectorStoreAdapter] = {}
        logger.info(f"RAGService initialized with llm_client={llm_client}, embedder={embedder}")
    
    async def _get_vector_store_adapter(self, vector_store_name: str) -> VectorStoreAdapter:
        """
        Get or create a vector store adapter for the specified vector store type.
        
        Args:
            vector_store_name: Name of the vector store type (e.g., "qdrant", "faiss").
            
        Returns:
            Vector store adapter instance.
        """
        if vector_store_name in self._vector_store_cache:
            return self._vector_store_cache[vector_store_name]
        
        try:
            # Get embedding dimension from embedder
            vector_dim = 1024  # Default fallback
            if hasattr(self.embedder, 'embedding_dimension'):
                vector_dim = self.embedder.embedding_dimension
                logger.debug(f"Using embedding dimension from embedder: {vector_dim}")
            
            # Create config based on vector store type
            config = self._get_vector_store_config(vector_store_name, vector_dim)
            
            # Create adapter
            adapter = VectorStoreRegistry.create_adapter(vector_store_name, config)
            
            # Connect
            await adapter.connect()
            
            # Cache instance
            self._vector_store_cache[vector_store_name] = adapter
            logger.info(f"Created and cached vector store adapter: {vector_store_name}")
            
            return adapter
            
        except Exception as e:
            logger.error(f"Failed to create vector store adapter for {vector_store_name}: {e}")
            raise
    
    def _get_vector_store_config(self, vector_store_name: str, vector_dim: int) -> VectorStoreConfig:
        """Get configuration for a vector store type."""
        from app.config.settings import settings
        
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
        
        if vector_store_name not in configs:
            available = list(configs.keys())
            raise ValueError(f"Unknown vector store: {vector_store_name}. Available: {available}")
        
        return configs[vector_store_name]

    def _get_strategy(self, rag_type: str, vector_store_adapter: VectorStoreAdapter):
        """
        Get the appropriate RAG strategy instance.
        
        Args:
            rag_type: Type of RAG strategy to use.
            vector_store_adapter: Vector store adapter to use.
            
        Returns:
            RAG strategy instance.
        """
        logger.debug(f"Selecting RAG strategy for rag_type='{rag_type}'")
        strategy_class = _get_strategy_class(rag_type.lower())

        logger.info(f"Instantiating RAG strategy: {strategy_class.__name__}")
        return strategy_class(
            vector_store_adapter=vector_store_adapter,
            llm_client=self.llm,
            embedder=self.embedder
        )

    async def execute_naive_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Naive RAG query with optional multimodal support."""
        logger.info(f"Executing naive RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("naive", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            }
        )
        logger.debug(f"Naive RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Naive RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Naive RAG execution failed: {e}")
            raise

    async def execute_advanced_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        rerank: bool = False,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Advanced RAG query with optional multimodal support."""
        logger.info(f"Executing advanced RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, rerank={rerank}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("advanced", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            rerank=rerank,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            }
        )
        logger.debug(f"Advanced RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Advanced RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Advanced RAG execution failed: {e}")
            raise

    async def execute_hierarchical_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        num_summaries: int = 3,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Hierarchical RAG query with optional multimodal support."""
        logger.info(f"Executing hierarchical RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, num_summaries={num_summaries}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("hierarchical", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "num_summaries": num_summaries,
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            },
        )
        logger.debug(f"Hierarchical RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Hierarchical RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Hierarchical RAG execution failed: {e}")
            raise

    async def execute_graph_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        traversal_depth: int = 2,
        relationship_types: list = None,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute GraphRAG query with optional multimodal support."""
        logger.info(f"Executing graph RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, traversal_depth={traversal_depth}, relationship_types={relationship_types}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("graph", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "traversal_depth": traversal_depth,
                "relationship_types": relationship_types,
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            },
        )
        logger.debug(f"Graph RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Graph RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Graph RAG execution failed: {e}")
            raise

    async def execute_agentic_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        max_iterations: int = 3,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Agentic RAG query with optional multimodal support."""
        logger.info(f"Executing agentic RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, max_iterations={max_iterations}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("agentic", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "max_iterations": max_iterations,
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            },
        )
        logger.debug(f"Agentic RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Agentic RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Agentic RAG execution failed: {e}")
            raise

    async def execute_hybrid_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        vector_weight: float = 0.7,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Hybrid RAG query with optional multimodal support."""
        logger.info(f"Executing hybrid RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', top_k={top_k}, vector_weight={vector_weight}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("hybrid", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            hybrid=True,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "vector_weight": vector_weight,
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            },
        )
        logger.debug(f"Hybrid RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Hybrid RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Hybrid RAG execution failed: {e}")
            raise

    async def execute_conversational_rag(
        self,
        query: str,
        vector_store_name: str,
        collection_name: str,
        session_id: str,
        top_k: int = 10,
        filters: Dict[str, Any] = None,
        memory_window: int = 5,
        score_threshold: float = 0.0,
        system_prompt: str = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None
    ) -> RAGResponse:
        """Execute Conversational RAG query with optional multimodal support."""
        logger.info(f"Executing conversational RAG query. Params: vector_store='{vector_store_name}', collection='{collection_name}', session_id='{session_id}', top_k={top_k}, memory_window={memory_window}, filters={filters}, score_threshold={score_threshold}, multimodal={query_image_base64 is not None or query_image_bytes is not None}")
        vector_store = await self._get_vector_store_adapter(vector_store_name)
        strategy = self._get_strategy("conversational", vector_store)
        config = RAGConfig(
            vector_store=vector_store_name,
            collection_name=collection_name,
            top_k=top_k,
            filters=filters,
            score_threshold=score_threshold,
            system_prompt=system_prompt,
            extra_params={
                "session_id": session_id,
                "memory_window": memory_window,
                "query_image_base64": query_image_base64,
                "query_image_bytes": query_image_bytes,
            },
        )
        logger.debug(f"Conversational RAG strategy config: {config}")
        try:
            result = await strategy.execute(query, config)
            logger.info(f"Conversational RAG execution successful: answer_length={len(result.answer) if result and getattr(result, 'answer', None) else 0}, sources_count={len(result.sources) if result and getattr(result, 'sources', None) else 0}")
            return result
        except Exception as e:
            logger.exception(f"Conversational RAG execution failed: {e}")
            raise

