# AI Document Knowledge Assistant — Frontend

A [Streamlit](https://streamlit.io) UI that connects to the FastAPI backend
(composed of the **IDP + RAG** bundles) over plain HTTP.

## Layout

```
frontend/
├── app.py            # Streamlit app (3 tabs: Upload / Ask / Chat)
├── api.py            # Thin HTTP client for the backend endpoints
└── requirements.txt  # Frontend-only deps
```

## 1. Start the backend (FastAPI)

From the repo root:

```bash
cp .env.example .env      # fill in BUCKET_NAME, MODEL_ID, EMBEDDING_MODEL_ID, etc.
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify: http://127.0.0.1:8000/api/health/ready  → 200 ready.

## 2. Start the frontend (Streamlit)

```bash
pip install -r frontend/requirements.txt
streamlit run frontend/app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

The sidebar lets you point at a different backend URL if you run it
elsewhere (or set the `AIMATIC_API_URL` env var).

## What each tab does

- **Upload documents**
  - Upload a file (PDF, DOCX, text, image…) → `POST /api/rag/ingestion/file`.
  - Paste raw text → `POST /api/rag/ingestion/text`.
  - Choose a Qdrant collection, chunk size/overlap, and chunker.
- **Ask questions**
  - Ask a natural-language question → `POST /api/rag/naive/query`.
  - Shows the generated answer plus the retrieved source excerpts + scores.
- **Chat**
  - Session-based Q&A via `/api/rag/chatbot/session` + `/api/rag/chatbot/chat`.

## Notes

- The backend must be reachable for anything to work — the sidebar shows a
  live connection status.
- Document ingestion requires a running Qdrant plus configured AWS (Textract,
  Bedrock) and an embedding model. See the repo root README and
  `.env.example` for that setup.
