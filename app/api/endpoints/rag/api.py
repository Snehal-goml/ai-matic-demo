"""RAG feature registration and dynamic strategy router inclusion."""

from __future__ import annotations

import importlib
import logging

from fastapi import APIRouter

from app.core.feature_contract import FeatureModule

logger = logging.getLogger(__name__)

router = APIRouter()

# Strategy option packs: (module path under endpoints.rag, URL sub-prefix, OpenAPI tag)
_STRATEGY_ROUTERS = (
    ("naive", "/naive", "Naive RAG"),
    ("advanced", "/advanced", "Advanced RAG"),
    ("hierarchical", "/hierarchical", "Hierarchical RAG"),
    ("graph", "/graph", "GraphRAG"),
    ("agentic", "/agentic", "Agentic RAG"),
    ("hybrid", "/hybrid", "Hybrid RAG"),
    ("conversational", "/conversational", "Conversational RAG"),
)


def _try_include_strategy(name: str, prefix: str, tag: str) -> bool:
    """Include a strategy router if its endpoint module is installed."""
    module_path = f"app.api.endpoints.rag.{name}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        logger.info("RAG strategy endpoint not installed, skipping: %s", name)
        return False
    except Exception as exc:
        logger.warning("Failed to import RAG strategy %s: %s", name, exc)
        return False

    strategy_router = getattr(module, "router", None)
    if strategy_router is None:
        logger.warning("RAG strategy module %s has no router", name)
        return False

    router.include_router(strategy_router, prefix=prefix, tags=[tag])
    logger.info("Included RAG strategy router: %s -> %s", name, prefix)
    return True


def _include_core_routers() -> None:
    """Always-on RAG usecase routers (ingestion + chatbot)."""
    from app.api.endpoints.rag import chatbot, ingestion

    router.include_router(ingestion.router, prefix="/ingestion", tags=["Document Ingestion"])
    router.include_router(chatbot.router, prefix="/chatbot", tags=["Chatbot"])


# Build feature router at import time from whatever strategy packs are present
_included: list[str] = []
for _name, _prefix, _tag in _STRATEGY_ROUTERS:
    if _try_include_strategy(_name, _prefix, _tag):
        _included.append(_name)
_include_core_routers()


@router.get("/", tags=["RAG"])
async def rag_root():
    """Optional feature root under /api/rag/."""
    from app.config.rag.registry import RAGStrategyRegistry, VectorStoreRegistry

    # Ensure option packs have registered themselves (lazy import)
    if not RAGStrategyRegistry.list_strategies():
        from app.core.pipelines.rag import _lazy_import_strategies

        _lazy_import_strategies()
    if not VectorStoreRegistry.list_adapters():
        from app.adapters.vector_store import _lazy_import_adapters

        _lazy_import_adapters()

    return {
        "message": "RAG feature API",
        "prefix": "/api/rag",
        "strategies_installed": _included,
        "strategies_registered": RAGStrategyRegistry.list_strategies(),
        "vector_stores": VectorStoreRegistry.list_adapters(),
        "endpoints": {
            "naive_query": "/api/rag/naive/query",
            "ingestion_file": "/api/rag/ingestion/file",
            "chatbot_chat": "/api/rag/chatbot/chat",
        },
    }


def _vector_store_ready() -> dict:
    """Optional readiness: report default vector store config presence (no hard connect)."""
    from app.config.settings import settings

    store = (settings.DEFAULT_VECTOR_STORE or "qdrant").lower()
    ok = True
    detail: dict = {"default_vector_store": store}
    if store == "qdrant":
        ok = bool(settings.QDRANT_URL)
    elif store == "milvus":
        ok = bool(settings.MILVUS_URI or settings.MILVUS_HOST)
    elif store == "pgvector":
        ok = bool(settings.POSTGRES_SERVER and settings.POSTGRES_DB)
    elif store == "neo4j":
        ok = bool(settings.NEO4J_URI or settings.NEO4J_HOST)
    elif store == "aws_opensearch":
        ok = bool(settings.AWS_OPENSEARCH_ENDPOINT)
    detail["success"] = ok
    return detail


def _validate_config() -> None:
    """Startup validation — soft checks only so subset ZIPs still boot."""
    from app.config.settings import settings

    if not settings.MODEL_ID and not settings.OPENAI_MODEL:
        logger.warning("No MODEL_ID / OPENAI_MODEL configured for RAG LLM calls")
    if not settings.EMBEDDING_MODEL_ID:
        logger.warning("EMBEDDING_MODEL_ID is not configured")
    logger.info(
        "RAG feature startup: strategies=%s default_store=%s",
        _included,
        settings.DEFAULT_VECTOR_STORE,
    )


FEATURE = FeatureModule(
    slug="rag",
    router=router,
    prefix="/api/rag",
    tags=["RAG"],
    health_checks={
        "vector_store_config": _vector_store_ready,
    },
    on_startup=_validate_config,
)
