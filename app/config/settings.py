"""Central application settings (composition root).

Each independently-composable feature owns its settings in a dedicated
package (``base_settings``, ``idp``, ``rag``, ``model_gateway``). This module
merges all of them into a single ``Settings`` object and exposes it through
two forms used across the codebase:

- ``get_settings()`` -> fresh (cached) ``Settings`` instance
- ``settings``        -> module-level singleton (``from app.config.settings import settings``)

It is also the **declaration of the selected solution bundles** for the
"AI Document Knowledge Assistant" demo.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.base_settings import BaseAppSettings
from app.config.idp.settings import IDPSettings
from app.config.model_gateway_settings import ModelGatewaySettings
from app.config.rag.settings import RAGSettings

# ---------------------------------------------------------------------------
# Solution bundle selection — AI Document Knowledge Assistant (demo)
# ---------------------------------------------------------------------------
# The business problem requires exactly two bundles whose capabilities line up
# end-to-end with the requested workflow:
#   1. Intelligent Document Processing (IDP): extract + process document
#      content, including OCR on scanned documents.
#   2. Retrieval-Augmented Generation (RAG): index content into a searchable,
#      vector-based knowledge repository and answer natural-language questions
#      grounded in the retrieved context.
SOLUTION_BUNDLES = ["idp", "rag"]

# Nested components / strategies chosen for the simplest production-ready build.
SOLUTION_COMPONENTS = {
    "solution_bundles": SOLUTION_BUNDLES,
    "idp": {
        "document_extractor": "AWS_textract",  # IDP Document Extractor
    },
    "rag": {
        "strategy": "naive",       # RAG Strategy
        "vector_store": "qdrant",  # Vector Store
        "top_k": 10,
        "score_threshold": 0.0,
        "vector_dim": 1536,
        "chunk_size": 1000,
        "chunk_overlap": 200,
    },
}


class Settings(
    BaseAppSettings,
    IDPSettings,
    RAGSettings,
    ModelGatewaySettings,
):
    """Complete application settings for the composed IDP + RAG app."""

    model_config = SettingsConfigDict(
        env_file=".env" if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached merged ``Settings`` instance (reads ``.env`` + env vars)."""
    return Settings()


# Module-level singleton so components can use ``from app.config.settings import settings``.
settings: Settings = get_settings()

# ---------------------------------------------------------------------------
# Export credentials/config read from .env into the process environment.
#
# pydantic-settings only loads ``.env`` into the Settings object; it does NOT
# populate ``os.environ``. The model gateway (and the OpenAI SDK) resolve
# credentials via ``os.getenv("OPENAI_API_KEY")`` / ``os.getenv("OPENAI_API_BASE")``,
# so without this export the RAG chat path fails with "Missing credentials".
# Existing process env vars always win (setdefault), and empty values are skipped.
# ---------------------------------------------------------------------------
for _name in (
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "LLM_PROVIDER",
    "MODEL_ID",
    "EMBEDDING_MODEL_ID",
    "NOVA_SONIC_MODEL_ID",
    "AWS_REGION",
):
    _value = getattr(settings, _name, "")
    if _value:
        os.environ.setdefault(_name, str(_value))