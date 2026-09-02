# Solution Bundle Selection — AI Document Knowledge Assistant

This document records **why** the two solution bundles and their nested
components were chosen for the *AI Document Knowledge Assistant*, and **where**
those choices are configured in this repository.

## Problem summary

Users upload business documents (PDFs, scanned documents, reports, policies,
manuals, invoices, …). The system must:

1. Extract content — **including OCR for scanned documents**.
2. Index everything into a **searchable knowledge repository**.
3. Answer **natural-language questions** grounded only in the uploaded content.
4. Retrieve the relevant documents **before** generating an answer.
5. Treat **multiple documents as one unified knowledge base**.
6. Use **vector-based semantic retrieval**.

## Selected configuration

| Configuration | Selection | Why it fits |
|---|---|---|
| Solution Bundles | ✅ **IDP + RAG** | IDP covers extraction/processing (incl. OCR); RAG covers indexing, retrieval and grounded Q&A. Together they satisfy the entire workflow end-to-end. |
| IDP Document Extractor | ✅ **AWS Textract** | Best-in-class OCR + document layout extraction for scanned PDFs/images; production-grade and directly meets the "including scanned documents" requirement. |
| RAG Strategy | ✅ **Naive RAG** | Simplest production-ready strategy: embed query → retrieve top-k → generate with context. Satisfies "retrieve before generate" with the fewest moving parts. |
| Vector Store | ✅ **Qdrant** | Purpose-built vector database for efficient semantic similarity search across many documents; unified multi-document collections. |

Why **exactly these two bundles**: the workflow has two distinct halves —
*ingest/understand documents* (IDP) and *search/answer from a knowledge base*
(RAG). Selecting any other two bundles would either not extract scanned
content, or not provide retrieval-augmented question answering.

## Requirements → mapping

| Requirement | Satisfied by |
|---|---|
| Support document extraction, incl. scanned documents | IDP bundle → AWS Textract (OCR) |
| Create a searchable knowledge repository | RAG bundle → ingestion pipeline chunking + embedding into Qdrant |
| Enable natural-language question answering | RAG bundle → Naive RAG LLM generation |
| Retrieve relevant info before generating | RAG bundle → Naive RAG `retrieve → generate` |
| Handle multiple docs as a unified KB | Qdrant collection(s) holding all chunks + metadata |
| Vector-based semantic retrieval | Qdrant vector similarity search (COSINE) |

## How it is wired in this repository

- **Bundle declaration** — `app/config/settings.py`
  - `SOLUTION_BUNDLES = ["idp", "rag"]`
  - `SOLUTION_COMPONENTS` pins `idp.document_extractor="AWS_textract"`,
    `rag.strategy="naive"`, `rag.vector_store="qdrant"`.
  - Merges the independent feature settings (`base + idp + rag + model_gateway`)
    into one `Settings` object exposed via `get_settings()` / `settings`.

- **App composition** — `app/main.py`
  - Mounts the **IDP** feature router under `/api/idp`
    (`app/api/endpoints/idp/api.py`, `FEATURE`).
  - Mounts the **RAG** feature router under `/api/rag`
    (`app/api/endpoints/rag/api.py`, `FEATURE`). Only the installed Naive RAG
    strategy endpoint is exposed (`app/api/endpoints/rag/naive.py`).
  - Shared health/readiness probes register each feature's checks under
    `/api/health/ready`.
  - `GET /api/config` reports the active bundle selection at runtime.

- **Nested component defaults**
  - IDP Document Extractor: `EXTRACTOR_TYPE=AWS_textract` — default in
    `app/config/idp/settings.py`, `.env.example`, and the factory
    `app/adapters/file_extraction/factory.py`.
  - RAG Strategy: `DEFAULT_RAG_TYPE="naive"` — `app/config/rag/settings.py`.
  - Vector Store: `DEFAULT_VECTOR_STORE="qdrant"` — `app/config/rag/settings.py`,
    registered in `app/config/rag/registry.py` and implemented by
    `app/adapters/vector_store/qdrant.py`.
  - S3 staging for Textract async PDF processing:
    `app/utils/s3_utils.py` (`S3Manager`, `create_s3_client`).

## Verify at runtime

```bash
cp .env.example .env          # set BUCKET_NAME, MODEL_ID, EMBEDDING_MODEL_ID, etc.
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- `GET /api/config` → shows `solution_bundles: ["idp","rag"]` and the components.
- `GET /api/health/ready` → `idp.extractor: "ok"`, `rag.vector_store_config.success: true`.
- `POST /api/rag/ingestion/file` → ingest a document into Qdrant.
- `POST /api/rag/naive/query` → ask a natural-language question.