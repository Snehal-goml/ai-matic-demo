"""
API Routes Aggregation

This module aggregates all endpoint routers into a single router.
"""

from fastapi import APIRouter

from app.api.endpoints import (
    naive_rag,
    advanced_rag,
    hierarchical_rag,
    graph_rag,
    agentic_rag,
    hybrid_rag,
    conversational_rag,
    ingestion,
    chatbot,
)

# Create the main router
all_routes = APIRouter()

# Include all RAG strategy routers
all_routes.include_router(
    naive_rag.router,
    prefix="/rag/naive",
    tags=["Naive RAG"]
)

all_routes.include_router(
    advanced_rag.router,
    prefix="/rag/advanced",
    tags=["Advanced RAG"]
)

all_routes.include_router(
    hierarchical_rag.router,
    prefix="/rag/hierarchical",
    tags=["Hierarchical RAG"]
)

all_routes.include_router(
    graph_rag.router,
    prefix="/rag/graph",
    tags=["GraphRAG"]
)

all_routes.include_router(
    agentic_rag.router,
    prefix="/rag/agentic",
    tags=["Agentic RAG"]
)

all_routes.include_router(
    hybrid_rag.router,
    prefix="/rag/hybrid",
    tags=["Hybrid RAG"]
)

all_routes.include_router(
    conversational_rag.router,
    prefix="/rag/conversational",
    tags=["Conversational RAG"]
)

# Include ingestion router
all_routes.include_router(
    ingestion.router,
    prefix="/ingestion",
    tags=["Document Ingestion"]
)

# Include unified chatbot router
all_routes.include_router(
    chatbot.router,
    prefix="/chatbot",
    tags=["Chatbot"]
)


# Health check endpoint
@all_routes.get("/health", tags=["Health"])
async def health_check():
    """Check API health and list available RAG strategies."""
    from app.config.registry import RAGStrategyRegistry, VectorStoreRegistry
    
    return {
        "status": "healthy",
        "rag_strategies": RAGStrategyRegistry.list_strategies(),
        "vector_stores": VectorStoreRegistry.list_adapters(),
    }


@all_routes.get("/", tags=["Root"])
async def root():
    """API root with documentation links."""
    return {
        "message": "Knowledge Augmentation Framework API",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "chatbot_session": "/chatbot/session",
            "chatbot_chat": "/chatbot/chat",
            "chatbot_sessions": "/chatbot/sessions",
            "naive_rag": "/rag/naive/query",
            "advanced_rag": "/rag/advanced/query",
            "hierarchical_rag": "/rag/hierarchical/query",
            "graph_rag": "/rag/graph/query",
            "agentic_rag": "/rag/agentic/query",
            "hybrid_rag": "/rag/hybrid/query",
            "conversational_rag": "/rag/conversational/query",
            "ingestion_file": "/ingestion/file",
            "ingestion_text": "/ingestion/text",
            "ingestion_directory": "/ingestion/directory",
            "ingestion_zip": "/ingestion/zip",
        }
    }

