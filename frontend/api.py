"""Thin HTTP client for the AI Document Knowledge Assistant backend.

These helpers wrap the FastAPI endpoints exposed by the app (which is composed
of the IDP + RAG bundles). The UI never talks to databases or AWS directly;
it only calls this HTTP API.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_S = 120


class BackendError(RuntimeError):
    """Raised when the backend returns a non-2xx response."""


def _get(base_url: str, path: str, timeout: int = TIMEOUT_S) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:  # connection refused, DNS, etc.
        raise BackendError(f"Cannot reach backend at {url}: {exc}") from exc
    if resp.status_code >= 400:
        raise BackendError(_extract_error(resp, url))
    return resp.json()


def _post_json(
    base_url: str, path: str, payload: dict, timeout: int = TIMEOUT_S
) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise BackendError(f"Cannot reach backend at {url}: {exc}") from exc
    if resp.status_code >= 400:
        raise BackendError(_extract_error(resp, url))
    return resp.json()


def _post_multipart(
    base_url: str,
    path: str,
    files: Dict[str, Any],
    data: Dict[str, Any],
    timeout: int = TIMEOUT_S,
) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        resp = requests.post(url, files=files, data=data, timeout=timeout)
    except requests.RequestException as exc:
        raise BackendError(f"Cannot reach backend at {url}: {exc}") from exc
    if resp.status_code >= 400:
        raise BackendError(_extract_error(resp, url))
    return resp.json()


def _extract_error(resp: requests.Response, url: str) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    detail = body.get("detail") or body.get("error") or body.get("message")
    if detail:
        if isinstance(detail, list):  # FastAPI validation errors
            parts = [f"{e.get('loc', '')}: {e.get('msg', '')}" for e in detail]
            return f"Validation error: {'; '.join(parts)}"
        return f"{resp.status_code} {detail}"
    return f"Backend returned {resp.status_code} for {url}"
# --------------------------------------------------------------------------- #
# Health / config
# --------------------------------------------------------------------------- #
def get_live(base_url: str) -> dict:
    return _get(base_url, "/api/health/live")


def get_ready(base_url: str) -> dict:
    return _get(base_url, "/api/health/ready")


def get_config(base_url: str) -> dict:
    return _get(base_url, "/api/config")


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
def ingest_file(
    base_url: str,
    file_bytes: bytes,
    filename: str,
    *,
    collection_name: str,
    vector_store: str = "qdrant",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    chunker_type: str = "fixed",
    loader_type: str = "auto",
    reset_collection: bool = False,
) -> dict:
    """Upload one document to /api/rag/ingestion/file (multipart form)."""
    files = {"file": (filename, file_bytes)}
    data = {
        "vector_store": vector_store,
        "collection_name": collection_name,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunker_type": chunker_type,
        "loader_type": loader_type,
        "reset_collection": str(reset_collection).lower(),
    }
    return _post_multipart(
        base_url, "/api/rag/ingestion/file", files=files, data=data
    )


def ingest_text(
    base_url: str,
    text: str,
    *,
    collection_name: str,
    vector_store: str = "qdrant",
    source: str = "direct_input",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    chunker_type: str = "fixed",
    reset_collection: bool = False,
) -> dict:
    """Send raw text to /api/rag/ingestion/text (multipart form)."""
    data = {
        "text": text,
        "vector_store": vector_store,
        "collection_name": collection_name,
        "source": source,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunker_type": chunker_type,
        "reset_collection": str(reset_collection).lower(),
    }
    return _post_multipart(
        base_url, "/api/rag/ingestion/text", files={}, data=data
    )
# --------------------------------------------------------------------------- #
# Naive RAG query
# --------------------------------------------------------------------------- #
def ask_naive(
    base_url: str,
    query: str,
    *,
    collection_name: str,
    vector_store: str = "qdrant",
    top_k: int = 5,
    score_threshold: float = 0.0,
    system_prompt: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> dict:
    """Ask a natural-language question via /api/rag/naive/query."""
    payload = {
        "query": query,
        "vector_store": vector_store,
        "collection_name": collection_name,
        "top_k": top_k,
        "score_threshold": score_threshold,
        "system_prompt": system_prompt,
        "filters": filters,
    }
    return _post_json(base_url, "/api/rag/naive/query", payload)


# --------------------------------------------------------------------------- #
# Chat session (unified chatbot)
# --------------------------------------------------------------------------- #
def create_chat_session(
    base_url: str,
    *,
    collection_name: str,
    rag_strategy: str = "naive",
    vector_store: str = "qdrant",
    top_k: int = 5,
) -> dict:
    """Create a chat session via /api/rag/chatbot/session."""
    payload = {
        "rag_strategy": rag_strategy,
        "vector_store": vector_store,
        "collection_name": collection_name,
        "retrieval_config": {"top_k": top_k, "score_threshold": 0.0},
    }
    return _post_json(base_url, "/api/rag/chatbot/session", payload)


def chat_message(
    base_url: str,
    session_id: str,
    message: str,
    *,
    top_k: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> dict:
    """Send a chat message via /api/rag/chatbot/chat."""
    payload: Dict[str, Any] = {"session_id": session_id, "message": message}
    if top_k is not None:
        payload["top_k"] = top_k
    if system_prompt:
        payload["system_prompt"] = system_prompt
    return _post_json(base_url, "/api/rag/chatbot/chat", payload)


def format_ingestion_result(result: dict) -> str:
    """Summarize an ingestion response for the UI."""
    return (
        f"Successfully ingested **{result.get('vectors_stored', 0)}** chunks "
        f"from **{result.get('total_documents', 0)}** document(s) into "
        f"`{result.get('collection_name', '')}`.\n\n"
        f"- Total chunks: {result.get('total_chunks')}\n"
        f"- Failed chunks: {result.get('failed_chunks')}"
    )