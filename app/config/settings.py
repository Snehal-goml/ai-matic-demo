"""Configuration for the AI Document Knowledge Assistant."""

import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --- LLM ---
LLM_PROVIDER = _get("LLM_PROVIDER", "openai")
MODEL_ID = _get("MODEL_ID", "gemini-2.0-flash")
EMBEDDING_MODEL_ID = _get("EMBEDDING_MODEL_ID", "gemini-embedding-001")
EMBEDDING_PROVIDER = _get("EMBEDDING_PROVIDER", "openai")

# --- OpenAI-compatible (Gemini) ---
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_API_BASE = _get("OPENAI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/openai/")

# --- AWS Bedrock ---
AWS_REGION = _get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = _get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = _get("AWS_SECRET_ACCESS_KEY")
BEDROCK_MAX_TOKENS = int(_get("BEDROCK_MAX_TOKENS", "1200"))

# --- Qdrant ---
QDRANT_URL = _get("QDRANT_URL", "http://localhost")
QDRANT_PORT = int(_get("QDRANT_PORT", "6333"))

# --- RAG defaults ---
DEFAULT_TOP_K = int(_get("DEFAULT_TOP_K", "5"))
DEFAULT_VECTOR_DIM = int(_get("DEFAULT_VECTOR_DIM", "3072"))
DEFAULT_CHUNK_SIZE = int(_get("DEFAULT_CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(_get("DEFAULT_CHUNK_OVERLAP", "200"))

# --- App ---
APP_TITLE = "AI Document Knowledge Assistant"
APP_VERSION = "1.0.0"
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
AUTH_METHOD = _get("AUTH_METHOD", "none")
