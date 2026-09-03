"""AI Document Knowledge Assistant - Backend.

A simple RAG (Retrieval-Augmented Generation) server that lets you:
- Upload documents (PDF, TXT, MD) into a Qdrant vector store
- Ask questions and get answers grounded in your documents
- Chat with memory across follow-up questions
- Get full-document summaries with download options
"""

import os
import json
import logging
import tempfile
import uuid
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config.settings import *

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _qdrant_url() -> str:
    return f"{QDRANT_URL}:{QDRANT_PORT}"


def _ensure_collection(name: str, dim: int = DEFAULT_VECTOR_DIM) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    url = f"{_qdrant_url()}/collections/{name}"
    try:
        r = http_requests.get(url, timeout=5)
        if r.status_code == 200:
            return  # already exists
    except Exception:
        pass
    # Create with cosine distance
    r = http_requests.put(
        url,
        json={"vectors": {"size": dim, "distance": "Cosine"}},
        timeout=10,
    )
    if r.status_code >= 400:
        raise HTTPException(500, f"Failed to create collection: {r.text}")


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the configured embedding provider."""
    if EMBEDDING_PROVIDER == "bedrock":
        return _embed_bedrock(texts)
    return _embed_openai(texts)


def _embed_openai(texts: list[str]) -> list[list[float]]:
    """Embed via OpenAI-compatible API (Gemini)."""
    r = http_requests.post(
        f"{OPENAI_API_BASE.rstrip('/')}/embeddings",
        json={"model": EMBEDDING_MODEL_ID, "input": texts},
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        timeout=60,
    )
    if r.status_code >= 400:
        raise HTTPException(500, f"Embedding failed: {r.text[:300]}")
    return [d["embedding"] for d in r.json()["data"]]


def _embed_bedrock(texts: list[str]) -> list[list[float]]:
    """Embed via AWS Bedrock (Titan)."""
    import boto3
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    vectors = []
    for t in texts:
        resp = client.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": t}),
        )
        vec = json.loads(resp["body"].read()).get("embedding", [])
        vectors.append(vec)
    return vectors


def _llm_chat(messages: list[dict], max_tokens: int = 1200) -> str:
    """Send a chat completion to the configured LLM."""
    if LLM_PROVIDER == "bedrock":
        return _llm_bedrock(messages, max_tokens)
    return _llm_openai(messages, max_tokens)


def _llm_openai(messages: list[dict], max_tokens: int) -> str:
    """Chat via OpenAI-compatible API (Gemini)."""
    r = http_requests.post(
        f"{OPENAI_API_BASE.rstrip('/')}/chat/completions",
        json={"model": MODEL_ID, "messages": messages, "max_tokens": max_tokens},
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        timeout=120,
    )
    if r.status_code >= 400:
        raise HTTPException(500, f"LLM error: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def _llm_bedrock(messages: list[dict], max_tokens: int) -> str:
    """Chat via AWS Bedrock (Converse API)."""
    import boto3
    client = boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
    )
    converse_msgs = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        converse_msgs.append({"role": role, "content": [{"text": str(m.get("content", ""))}]})
    resp = client.converse(
        modelId=MODEL_ID,
        messages=converse_msgs,
        inferenceConfig={"maxTokens": max_tokens},
    )
    # Collect text blocks (skip reasoningContent)
    parts = []
    for block in resp.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            parts.append(block["text"])
    return "".join(parts)


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from PDF bytes."""
    try:
        import pdfplumber
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            text = ""
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages:
                    text += (page.extract_text() or "") + "\n"
            return text
        finally:
            os.unlink(tmp_path)
    except ImportError:
        pass
    # Fallback to pypdf
    import pypdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        reader = pypdf.PdfReader(tmp_path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    finally:
        os.unlink(tmp_path)


def _chunk_text(text: str, size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return [c for c in chunks if c.strip()]


# --------------------------------------------------------------------------- #
# In-memory chat sessions
# --------------------------------------------------------------------------- #

chat_sessions: dict[str, list[dict]] = {}


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class QueryRequest(BaseModel):
    query: str
    collection_name: str = "company_docs"
    vector_store: str = "qdrant"
    top_k: int = 5
    score_threshold: float = 0.0
    system_prompt: Optional[str] = None


class SessionRequest(BaseModel):
    collection_name: str = "company_docs"
    top_k: int = 5


class ChatRequest(BaseModel):
    session_id: str
    message: str
    top_k: Optional[int] = None
    system_prompt: Optional[str] = None


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/live")
def live():
    return {"status": "ok"}


@app.get("/api/health/ready")
def ready():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "llm_provider": LLM_PROVIDER,
        "model": MODEL_ID,
        "embedding_model": EMBEDDING_MODEL_ID,
        "vector_store": DEFAULT_VECTOR_STORE,
    }


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #

@app.post("/api/rag/ingestion/file")
async def ingest_file(
    file: UploadFile = File(...),
    collection_name: str = Form("company_docs"),
    chunk_size: int = Form(DEFAULT_CHUNK_SIZE),
    chunk_overlap: int = Form(DEFAULT_CHUNK_OVERLAP),
):
    """Upload a file, extract text, chunk, embed, and store in Qdrant."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")

    filename = file.filename or "document"
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        text = _extract_pdf_text(content)
    elif ext in (".txt", ".md", ".text"):
        text = content.decode("utf-8", errors="replace")
    else:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    if not text.strip():
        raise HTTPException(422, "No text extracted (scanned image?)")

    chunks = _chunk_text(text, chunk_size, chunk_overlap)
    if not chunks:
        raise HTTPException(422, "No chunks produced")

    # Add source metadata to each chunk
    tagged = [f"[Source: {filename}]\n{c}" for c in chunks]
    vectors = _embed_texts(tagged)

    _ensure_collection(collection_name)

    # Store in Qdrant
    url = f"{_qdrant_url()}/collections/{collection_name}/points"
    points = [
        {"id": str(uuid.uuid4()), "vector": v, "payload": {"text": t, "source": filename}}
        for t, v in zip(tagged, vectors)
    ]
    r = http_requests.put(url, json={"points": points}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(500, f"Qdrant error: {r.text[:300]}")

    return {
        "filename": filename,
        "total_documents": 1,
        "total_chunks": len(chunks),
        "vectors_stored": len(points),
        "failed_chunks": 0,
        "collection_name": collection_name,
    }


@app.post("/api/rag/ingestion/text")
async def ingest_text(
    text: str = Form(...),
    collection_name: str = Form("company_docs"),
    source: str = Form("direct_input"),
    chunk_size: int = Form(DEFAULT_CHUNK_SIZE),
    chunk_overlap: int = Form(DEFAULT_CHUNK_OVERLAP),
):
    """Ingest raw text into the knowledge base."""
    if not text.strip():
        raise HTTPException(400, "Empty text")

    chunks = _chunk_text(text, chunk_size, chunk_overlap)
    tagged = [f"[Source: {source}]\n{c}" for c in chunks]
    vectors = _embed_texts(tagged)

    _ensure_collection(collection_name)

    url = f"{_qdrant_url()}/collections/{collection_name}/points"
    points = [
        {"id": str(uuid.uuid4()), "vector": v, "payload": {"text": t, "source": source}}
        for t, v in zip(tagged, vectors)
    ]
    r = http_requests.put(url, json={"points": points}, timeout=30)
    if r.status_code >= 400:
        raise HTTPException(500, f"Qdrant error: {r.text[:300]}")

    return {
        "filename": source,
        "total_documents": 1,
        "total_chunks": len(chunks),
        "vectors_stored": len(points),
        "failed_chunks": 0,
        "collection_name": collection_name,
    }


# --------------------------------------------------------------------------- #
# Naive RAG query
# --------------------------------------------------------------------------- #

@app.post("/api/rag/naive/query")
def naive_query(req: QueryRequest):
    """Retrieve relevant chunks and generate a grounded answer."""
    # 1. Embed the query
    qvec = _embed_texts([req.query])[0]

    # 2. Search Qdrant
    url = f"{_qdrant_url()}/collections/{req.collection_name}/points/query"
    r = http_requests.post(
        url,
        json={
            "query": qvec,
            "limit": req.top_k,
            "with_payload": True,
            "score_threshold": req.score_threshold,
        },
        timeout=10,
    )
    if r.status_code >= 400:
        raise HTTPException(500, f"Qdrant error: {r.text[:300]}")

    hits = r.json().get("result", [])
    if not hits:
        return {
            "answer": "I couldn't find relevant information in your documents.",
            "sources": [],
            "confidence": 0.0,
            "rag_type": "naive",
            "vector_store": "qdrant",
        }

    # 3. Build context
    context_parts = []
    sources = []
    for h in hits:
        payload = h.get("payload", {})
        text = payload.get("text", "")
        source = payload.get("source", "unknown")
        score = h.get("score", 0)
        context_parts.append(f"[Source: {source}]\n{text}")
        sources.append({"source": source, "score": round(score, 3), "text": text[:200]})

    context = "\n\n".join(context_parts)

    # 4. Generate answer
    system = req.system_prompt or (
        "You are a helpful assistant. Answer using ONLY the provided context. "
        "If the context doesn't contain the answer, say so clearly. "
        "Be concise and accurate."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {req.query}"},
    ]
    answer = _llm_chat(messages)

    # 5. Simple confidence: average of top scores
    avg_score = sum(h.get("score", 0) for h in hits) / len(hits) if hits else 0

    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(avg_score, 3),
        "rag_type": "naive",
        "vector_store": "qdrant",
    }


# --------------------------------------------------------------------------- #
# Full-document summary
# --------------------------------------------------------------------------- #

@app.post("/api/rag/naive/summarize-document")
async def summarize_document(file: UploadFile = File(...)):
    """Extract full text from a file and summarize it."""
    content = await file.read()
    filename = file.filename or "document"
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        text = _extract_pdf_text(content)
    elif ext in (".txt", ".md", ".text"):
        text = content.decode("utf-8", errors="replace")
    else:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    if not text.strip():
        raise HTTPException(422, "No text extracted")

    # Cap at 120k chars to stay within context limits
    truncated = len(text) > 120_000
    if truncated:
        text = text[:120_000]

    prompt = (
        "Provide a structured summary of this document with these sections:\n"
        "## Overview\n## Main Sections\n## Key Findings\n## Conclusions\n\n"
        "Be faithful to the document. Do not invent facts.\n\n"
        f"Document:\n{text}"
    )
    answer = _llm_chat([{"role": "user", "content": prompt}])

    return {
        "filename": filename,
        "summary": answer,
        "characters_analyzed": len(text),
        "truncated": truncated,
    }


# --------------------------------------------------------------------------- #
# Chat session (with memory)
# --------------------------------------------------------------------------- #

@app.post("/api/rag/chatbot/session")
def create_session(req: SessionRequest):
    """Create a new chat session."""
    sid = str(uuid.uuid4())
    chat_sessions[sid] = []
    return {"session_id": sid, "collection_name": req.collection_name}


@app.post("/api/rag/chatbot/chat")
def chat(req: ChatRequest):
    """Send a message in a chat session and get a grounded answer."""
    history = chat_sessions.get(req.session_id)
    if history is None:
        raise HTTPException(404, "Session not found")

    # Retrieve relevant chunks
    top_k = req.top_k or 5
    qvec = _embed_texts([req.message])[0]
    url = f"{_qdrant_url()}/collections/company_docs/points/query"
    r = http_requests.post(
        url,
        json={"query": qvec, "limit": top_k, "with_payload": True},
        timeout=10,
    )
    if r.status_code >= 400:
        raise HTTPException(500, f"Qdrant error: {r.text[:300]}")

    hits = r.json().get("result", [])
    context_parts = []
    sources = []
    for h in hits:
        payload = h.get("payload", {})
        text = payload.get("text", "")
        source = payload.get("source", "unknown")
        score = h.get("score", 0)
        context_parts.append(f"[Source: {source}]\n{text}")
        sources.append({"source": source, "score": round(score, 3), "text": text[:200]})

    context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."

    # Build conversation history + new message
    system = req.system_prompt or (
        "You are a helpful assistant. Answer using ONLY the provided context. "
        "If the context doesn't contain the answer, say so."
    )
    messages = [{"role": "system", "content": system}]
    for h in history:
        messages.append(h)
    messages.append({"role": "user", "content": f"Context:\n{context}\n\nQuestion: {req.message}"})

    answer = _llm_chat(messages)

    # Store in session history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": answer})

    avg_score = sum(h.get("score", 0) for h in hits) / len(hits) if hits else 0

    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(avg_score, 3),
        "session_id": req.session_id,
    }


# --------------------------------------------------------------------------- #
# Root
# --------------------------------------------------------------------------- #

@app.get("/")
def root():
    return {
        "message": "AI Document Knowledge Assistant",
        "docs": "/docs",
        "config": "/api/config",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
