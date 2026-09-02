"""
RAG API Schemas

Pydantic models for RAG endpoint request/response validation.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class VectorStoreType(str, Enum):
    """Supported vector store types."""
    QDRANT = "qdrant"
    MILVUS = "milvus"
    PGVECTOR = "pgvector"
    OPENSEARCH = "opensearch"
    AWS_OPENSEARCH = "aws_opensearch"
    FAISS = "faiss"
    NEO4J = "neo4j"


class SourceDocument(BaseModel):
    """Source document information in response."""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = {}
    source: Optional[str] = None


class RAGQueryRequest(BaseModel):
    """Base request model for all RAG queries."""
    query: str = Field(
        default="",
        description="The user query text (optional if using image query)"
    )
    vector_store: VectorStoreType = Field(
        default=VectorStoreType.QDRANT,
        description="Vector store to use for retrieval"
    )
    collection_name: str = Field(
        default="default",
        description="Name of the collection to search"
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of documents to retrieve"
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata filters for retrieval"
    )
    score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold"
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Optional custom system prompt for generation"
    )
    # Multimodal support
    query_image_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded image for multimodal query (alternative to query text)"
    )

    class Config:
        use_enum_values = True


class AdvancedRAGRequest(RAGQueryRequest):
    """Request model for Advanced RAG with reranking."""
    rerank: bool = Field(
        default=False,
        description="Whether to apply reranking to results"
    )
    expand_query: bool = Field(
        default=True,
        description="Whether to expand the query for better retrieval"
    )


class HierarchicalRAGRequest(RAGQueryRequest):
    """Request model for Hierarchical RAG."""
    num_summaries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top-level summaries to retrieve"
    )


class GraphRAGRequest(RAGQueryRequest):
    """Request model for GraphRAG. GraphRAG requires Neo4j as the vector store."""
    vector_store: VectorStoreType = Field(
        default=VectorStoreType.NEO4J,
        description="Vector store to use for retrieval (must be Neo4j for GraphRAG)"
    )
    traversal_depth: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Depth of graph traversal"
    )
    relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Specific relationship types to traverse"
    )

    @field_validator("vector_store")
    @classmethod
    def require_neo4j(cls, value):
        store = value.value if isinstance(value, VectorStoreType) else value
        if store != VectorStoreType.NEO4J.value:
            raise ValueError("GraphRAG requires Neo4j as the vector store")
        return value


class AgenticRAGRequest(RAGQueryRequest):
    """Request model for Agentic RAG."""
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retrieval iterations"
    )


class HybridRAGRequest(RAGQueryRequest):
    """Request model for Hybrid RAG."""
    vector_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Weight for vector search (1-weight for keyword)"
    )


class ConversationalRAGRequest(RAGQueryRequest):
    """Request model for Conversational RAG."""
    session_id: str = Field(
        ...,
        description="Session ID for conversation tracking"
    )
    memory_window: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of previous messages to consider"
    )


class RAGResponse(BaseModel):
    """Standard response model for all RAG queries."""
    answer: str = Field(..., description="Generated answer")
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="Source documents used for the answer"
    )
    rag_type: str = Field(..., description="Type of RAG strategy used")
    vector_store: str = Field(..., description="Vector store used")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score of the answer"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the query execution"
    )


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    vector_stores: Dict[str, bool]
    rag_strategies: List[str]


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    status_code: int

