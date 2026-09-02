"""AI Document Knowledge Assistant — Streamlit frontend (single screen).

Connects to the FastAPI backend (IDP + RAG bundles) over HTTP using the thin
client in ``api.py``. Launch with:

    streamlit run frontend/app.py

Everything lives on one screen:
  * Main area — a single chat: type a question, get a grounded answer with
    sources. Conversation history is kept (no session management needed; each
    question is an independent Naive-RAG lookup).
  * Sidebar — backend status, collection selector, Top-K, and document
    upload (file or pasted text) with sensible defaults.
"""

from __future__ import annotations

import os

import streamlit as st

from api import (  # noqa: E402  (frontend dir added to sys.path by the launcher)
    BackendError,
    DEFAULT_BASE_URL,
    ask_naive,
    format_ingestion_result,
    get_config,
    get_live,
    get_ready,
    ingest_file,
    ingest_text,
)

st.set_page_config(
    page_title="AI Document Knowledge Assistant",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _backend_base() -> str:
    return os.environ.get("AIMATIC_API_URL", DEFAULT_BASE_URL).rstrip("/")


# --------------------------------------------------------------------------- #
# Sidebar: status, knowledge-base controls, and document upload
# --------------------------------------------------------------------------- #
def render_sidebar() -> str:
    with st.sidebar:
        st.header("⚙️ Settings")
        base = st.text_input(
            "Backend URL",
            value=_backend_base(),
            help="FastAPI base URL (defaults to AIMATIC_API_URL env or localhost).",
        )
        base = base.rstrip("/")

        st.divider()
        ok = True
        try:
            live = get_live(base)
            ready = get_ready(base)
            ok = live.get("status") == "ok" and ready.get("status") == "ready"
            st.success("Backend online & ready" if ok else "Backend online")
        except BackendError as exc:
            st.error(f"Backend unreachable: {exc}")
            st.warning("Start it with: `uvicorn app.main:app --port 8000`")

        if ok:
            try:
                cfg = get_config(base)
                active = cfg.get("active", {})
                st.caption(
                    f"Extractor: `{active.get('extractor')}` · "
                    f"RAG: `{active.get('rag_strategy')}` · "
                    f"Store: `{active.get('vector_store')}`"
                )
            except BackendError:
                pass

        st.divider()
        st.subheader("📚 Knowledge base")
        st.text_input(
            "Collection",
            key="collection",
            value=st.session_state.get("collection", "company_docs"),
        )
        st.slider("Top-K", 1, 20, 5, key="top_k")
        if st.button("🧹 Clear conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

        st.divider()
        st.subheader("📤 Add documents")

        uploaded = st.file_uploader(
            "Upload a file",
            type=["pdf", "txt", "md", "json", "jsonl", "png", "jpg", "jpeg", "tiff"],
            key="file_uploader",
        )
        if st.button(
            "Ingest file",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        ):
            try:
                with st.spinner("Extracting, chunking, and embedding…"):
                    result = ingest_file(
                        base,
                        uploaded.getvalue(),
                        uploaded.name,
                        collection_name=st.session_state.collection.strip() or "company_docs",
                    )
                st.session_state.ingest_msg = ("ok", format_ingestion_result(result))
            except BackendError as exc:
                st.session_state.ingest_msg = ("err", str(exc))
            st.rerun()

        with st.expander("…or paste text"):
            source = st.text_input("Source label", value="direct_input", key="src_label")
            text = st.text_area(
                "Document text",
                height=140,
                placeholder="Paste a policy, manual excerpt, report snippet …",
                key="paste_text",
            )
            if st.button(
                "Ingest text",
                type="primary",
                use_container_width=True,
            ):
                if not text.strip():
                    st.warning("Enter some text to ingest.")
                else:
                    try:
                        with st.spinner("Chunking and embedding…"):
                            result = ingest_text(
                                base,
                                text,
                                collection_name=st.session_state.collection.strip() or "company_docs",
                                source=source.strip() or "direct_input",
                            )
                        st.session_state.ingest_msg = ("ok", format_ingestion_result(result))
                    except BackendError as exc:
                        st.session_state.ingest_msg = ("err", str(exc))
                    st.rerun()

    return base


# --------------------------------------------------------------------------- #
# Shared source rendering
# --------------------------------------------------------------------------- #
def _render_sources(sources: list) -> None:
    if not sources:
        st.info("No source documents retrieved.")
        return
    with st.expander(f"Retrieved context ({len(sources)})", expanded=False):
        for i, src in enumerate(sources, start=1):
            score = src.get("score", 0.0)
            source_name = src.get("source") or src.get("metadata", {}).get(
                "source", "unknown"
            )
            st.markdown(f"**#{i}** · `{source_name}` · score **{score:.3f}**")
            st.write(src.get("content", ""))


# --------------------------------------------------------------------------- #
# Main screen: one chat does everything
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("📄 AI Document Knowledge Assistant")
    base = render_sidebar()

    # Show the last upload result as a toast so the chat stays uncluttered.
    msg = st.session_state.pop("ingest_msg", None)
    if msg:
        (st.toast if msg[0] == "ok" else st.error)(msg[1])

    st.caption(
        "Ask anything about your documents — answers come only from the "
        "knowledge base (Naive RAG), with sources under each reply. "
        "Upload documents in the sidebar to grow the knowledge base."
    )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []  # list of (role, text, sources)

    if not st.session_state.chat_history:
        st.info("👈 Start by uploading a document (sidebar), then ask a question here.")

    # Transcript
    for role, text, sources in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(text)
            if role == "assistant":
                _render_sources(sources)

    if prompt := st.chat_input("Ask about your documents…"):
        collection = st.session_state.collection.strip() or "company_docs"
        st.session_state.chat_history.append(("user", prompt, []))
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Retrieving context and generating answer…"):
                try:
                    resp = ask_naive(
                        base,
                        prompt,
                        collection_name=collection,
                        top_k=int(st.session_state.top_k),
                    )
                    answer = resp.get("answer", "—")
                    sources = resp.get("sources", [])
                    st.markdown(answer)
                    st.caption(
                        f"Confidence: **{resp.get('confidence', 0):.3f}** · "
                        f"Collection: `{collection}` · Store: `{resp.get('vector_store', 'qdrant')}`"
                    )
                    _render_sources(sources)
                except BackendError as exc:
                    answer = f"⚠️ {exc}"
                    sources = []
                    st.markdown(answer)
        st.session_state.chat_history.append(("assistant", answer, sources))

    st.divider()
    st.caption(
        f"Backend API: `{base}/docs` · Powered by IDP (AWS Textract) + Naive RAG (Qdrant)"
    )


main()
