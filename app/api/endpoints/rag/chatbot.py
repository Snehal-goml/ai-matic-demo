"""
Unified Chatbot Endpoint

Single endpoint for RAG chatbot with session management.
Allows users to create sessions with their choice of RAG strategy
and vector store, then chat using that configuration.
"""

import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.api.schemas.rag.chatbot import (
    CreateSessionRequest,
    UpdateSessionRequest,
    SessionResponse,
    SessionListResponse,
    ChatRequest,
    ChatResponse,
    ErrorResponse,
)
from app.services.rag.chatbot_service import ChatbotService
from app.api.dependencies.rag import get_rag_components

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_chatbot_service(components: dict = Depends(get_rag_components)) -> ChatbotService:
    """Dependency to get ChatbotService instance."""
    logger.debug("Initializing ChatbotService with components")
    return ChatbotService(
        llm_client=components["llm"],
        embedder=components["embedder"]
    )


# ============== Session Management Endpoints ==============

@router.post(
    "/session",
    response_model=SessionResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Create Chat Session",
    description="Create a new chat session with specified RAG strategy and vector store."
)
async def create_session(
    request: CreateSessionRequest,
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    Create a new chat session.
    
    Configure the RAG strategy, vector store, and other parameters.
    Returns a session_id to use for subsequent chat requests.
    
    Available RAG strategies:
    - naive: Simple single-pass retrieval and generation
    - advanced: Query expansion and reranking
    - hierarchical: Multi-level document retrieval with summaries
    - graph: Graph-based retrieval with relationship traversal (requires Neo4j)
    - agentic: Iterative retrieval with agent-based reasoning
    - hybrid: Combined vector and keyword search
    - conversational: Context-aware with conversation memory
    
    Available vector stores:
    - qdrant, milvus, pgvector, opensearch, aws_opensearch, faiss, neo4j
    """
    logger.info(
        f"Creating session: rag_strategy={request.rag_strategy}, "
        f"vector_store={request.vector_store}, collection={request.collection_name}"
    )
    try:
        session = service.create_session(request)
        logger.info(f"Session created: {session.session_id}")
        return session
    except Exception as e:
        logger.error(f"Failed to create session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/session/{session_id}",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get Session",
    description="Retrieve session configuration by ID."
)
async def get_session(
    session_id: str,
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    Get session details by ID.
    
    Returns the current configuration including RAG strategy,
    vector store, and all settings.
    """
    logger.debug(f"Getting session: {session_id}")
    session = service.get_session(session_id)
    if not session:
        logger.warning(f"Session not found: {session_id}")
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


@router.patch(
    "/session/{session_id}",
    response_model=SessionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Update Session",
    description="Update session configuration. Use this to switch RAG strategy or vector store."
)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    Update session configuration.
    
    Allows switching:
    - RAG strategy (e.g., from naive to advanced)
    - Vector store (e.g., from qdrant to faiss)
    - Collection name
    - Retrieval and generation settings
    
    Only provided fields will be updated; others remain unchanged.
    """
    logger.info(f"Updating session {session_id}: {request.model_dump(exclude_none=True)}")
    try:
        session = service.update_session(session_id, request)
        if not session:
            logger.warning(f"Session not found for update: {session_id}")
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        logger.info(f"Session updated: {session_id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/session/{session_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Delete Session",
    description="End and delete a chat session."
)
async def delete_session(
    session_id: str,
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    Delete a session.
    
    Ends the session and cleans up any associated resources.
    The session_id will no longer be valid for chat requests.
    """
    logger.info(f"Deleting session: {session_id}")
    deleted = service.delete_session(session_id)
    if not deleted:
        logger.warning(f"Session not found for deletion: {session_id}")
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"message": f"Session {session_id} deleted successfully"}


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="List Sessions",
    description="List all active chat sessions."
)
async def list_sessions(
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    List all active sessions.
    
    Returns a list of all current sessions with their configurations.
    """
    logger.debug("Listing all sessions")
    try:
        sessions = service.list_sessions()
        return SessionListResponse(sessions=sessions, total=len(sessions))
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============== Chat Endpoint ==============

@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Chat",
    description="Send a message and get a response using the session's RAG configuration."
)
async def chat(
    request: ChatRequest,
    service: ChatbotService = Depends(_get_chatbot_service)
):
    """
    Send a chat message and receive a RAG-powered response.
    
    The message is processed using the RAG strategy and vector store
    configured in the session. You can optionally override certain
    parameters like top_k and filters for this specific request.
    
    Supports:
    - Text queries via `message` field
    - Image queries via `query_image_base64` field
    - Combined text + image queries
    
    The response includes:
    - Generated answer
    - Source documents used
    - Confidence score
    - Metadata about the query execution
    """
    logger.info(
        f"Chat request: session_id={request.session_id}, "
        f"message_length={len(request.message or '')}, "
        f"has_image={request.query_image_base64 is not None}"
    )
    
    if not request.message and not request.query_image_base64:
        raise HTTPException(
            status_code=400,
            detail="Must provide either message or query_image_base64"
        )
    
    try:
        response = await service.chat(request)
        logger.info(
            f"Chat response: session_id={request.session_id}, "
            f"answer_length={len(response.answer)}, "
            f"sources_count={len(response.sources)}, "
            f"confidence={response.confidence}"
        )
        return response
    except ValueError as e:
        # Session not found or invalid configuration
        logger.warning(f"Chat request failed (ValueError): {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Chat request failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

