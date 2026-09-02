"""
Chatbot Service

Business logic for unified chatbot operations.
Wraps RAGService and SessionManager to provide a unified interface.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

from app.services.rag.retrieval_service import RAGService
from app.api.schemas.rag.chatbot import (
    CreateSessionRequest,
    UpdateSessionRequest,
    SessionResponse,
    ChatRequest,
    ChatResponse,
    SourceDocument,
    RetrievalConfigRequest,
    GenerationConfigRequest,
    StrategySpecificConfig,
)

logger = logging.getLogger(__name__)


class ChatSession:
    """
    Represents a chat session with its configuration.
    
    Stores the RAG strategy, vector store, and other configuration
    for a user's chat session.
    """
    
    def __init__(
        self,
        session_id: str,
        rag_strategy: str,
        vector_store: str,
        collection_name: str,
        retrieval_config: Dict[str, Any],
        generation_config: Dict[str, Any],
        strategy_config: Dict[str, Any],
        metadata: Dict[str, Any],
        created_at: datetime
    ):
        self.session_id = session_id
        self.rag_strategy = rag_strategy
        self.vector_store = vector_store
        self.collection_name = collection_name
        self.retrieval_config = retrieval_config
        self.generation_config = generation_config
        self.strategy_config = strategy_config
        self.metadata = metadata
        self.created_at = created_at
    
    def to_response(self) -> SessionResponse:
        """Convert to SessionResponse model."""
        return SessionResponse(
            session_id=self.session_id,
            rag_strategy=self.rag_strategy,
            vector_store=self.vector_store,
            collection_name=self.collection_name,
            retrieval_config=self.retrieval_config,
            generation_config=self.generation_config,
            strategy_config=self.strategy_config,
            created_at=self.created_at,
            metadata=self.metadata
        )


class ChatbotSessionManager:
    """
    Manages chatbot sessions.
    
    In-memory session storage. For production, replace with
    a persistent store (Redis, DynamoDB, PostgreSQL, etc.).
    """
    
    _sessions: Dict[str, ChatSession] = {}
    
    @classmethod
    def create_session(cls, request: CreateSessionRequest) -> ChatSession:
        """
        Create a new chat session.
        
        Args:
            request: Session creation request with configuration.
            
        Returns:
            Created ChatSession instance.
        """
        session_id = str(uuid.uuid4())
        
        # Build retrieval config
        retrieval_config = {}
        if request.retrieval_config:
            retrieval_config = request.retrieval_config.model_dump(exclude_none=True)
        else:
            retrieval_config = RetrievalConfigRequest().model_dump()
        
        # Build generation config
        generation_config = {}
        if request.generation_config:
            generation_config = request.generation_config.model_dump(exclude_none=True)
        else:
            generation_config = GenerationConfigRequest().model_dump()
        
        # Build strategy config
        strategy_config = {}
        if request.strategy_config:
            strategy_config = request.strategy_config.model_dump(exclude_none=True)
        else:
            strategy_config = StrategySpecificConfig().model_dump()
        
        session = ChatSession(
            session_id=session_id,
            rag_strategy=request.rag_strategy,
            vector_store=request.vector_store,
            collection_name=request.collection_name,
            retrieval_config=retrieval_config,
            generation_config=generation_config,
            strategy_config=strategy_config,
            metadata=request.metadata,
            created_at=datetime.utcnow()
        )
        
        cls._sessions[session_id] = session
        logger.info(f"Created chat session: {session_id} with RAG={request.rag_strategy}, VectorStore={request.vector_store}")
        
        return session
    
    @classmethod
    def get_session(cls, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID."""
        return cls._sessions.get(session_id)
    
    @classmethod
    def update_session(cls, session_id: str, request: UpdateSessionRequest) -> Optional[ChatSession]:
        """
        Update an existing session.
        
        Args:
            session_id: Session to update.
            request: Update request with new values.
            
        Returns:
            Updated session or None if not found.
        """
        session = cls._sessions.get(session_id)
        if not session:
            return None
        
        # Update fields if provided
        if request.rag_strategy is not None:
            session.rag_strategy = request.rag_strategy
            logger.info(f"Session {session_id}: Switched RAG strategy to {request.rag_strategy}")
        
        if request.vector_store is not None:
            session.vector_store = request.vector_store
            logger.info(f"Session {session_id}: Switched vector store to {request.vector_store}")
        
        if request.collection_name is not None:
            session.collection_name = request.collection_name
        
        if request.retrieval_config is not None:
            session.retrieval_config.update(
                request.retrieval_config.model_dump(exclude_none=True)
            )
        
        if request.generation_config is not None:
            session.generation_config.update(
                request.generation_config.model_dump(exclude_none=True)
            )
        
        if request.strategy_config is not None:
            session.strategy_config.update(
                request.strategy_config.model_dump(exclude_none=True)
            )
        
        if request.metadata is not None:
            session.metadata.update(request.metadata)
        
        return session
    
    @classmethod
    def delete_session(cls, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session to delete.
            
        Returns:
            True if deleted, False if not found.
        """
        if session_id in cls._sessions:
            del cls._sessions[session_id]
            logger.info(f"Deleted chat session: {session_id}")
            return True
        return False
    
    @classmethod
    def list_sessions(cls) -> List[ChatSession]:
        """List all active sessions."""
        return list(cls._sessions.values())
    
    @classmethod
    def clear_all(cls) -> None:
        """Clear all sessions."""
        cls._sessions.clear()
        logger.info("Cleared all chat sessions")


class ChatbotService:
    """
    Service for chatbot operations.
    
    Provides unified interface for session management and chat functionality.
    """
    
    def __init__(self, llm_client: Any, embedder: Any):
        """
        Initialize the chatbot service.
        
        Args:
            llm_client: LLM client for generation.
            embedder: Embedding client.
        """
        self.rag_service = RAGService(llm_client=llm_client, embedder=embedder)
        logger.info("ChatbotService initialized")
    
    def create_session(self, request: CreateSessionRequest) -> SessionResponse:
        """
        Create a new chat session.
        
        Args:
            request: Session creation request.
            
        Returns:
            Created session response.
        """
        session = ChatbotSessionManager.create_session(request)
        return session.to_response()
    
    def get_session(self, session_id: str) -> Optional[SessionResponse]:
        """
        Get session by ID.
        
        Args:
            session_id: Session ID to retrieve.
            
        Returns:
            Session response or None if not found.
        """
        session = ChatbotSessionManager.get_session(session_id)
        if session:
            return session.to_response()
        return None
    
    def update_session(self, session_id: str, request: UpdateSessionRequest) -> Optional[SessionResponse]:
        """
        Update session configuration.
        
        Args:
            session_id: Session to update.
            request: Update request.
            
        Returns:
            Updated session response or None if not found.
        """
        session = ChatbotSessionManager.update_session(session_id, request)
        if session:
            return session.to_response()
        return None
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session to delete.
            
        Returns:
            True if deleted, False if not found.
        """
        return ChatbotSessionManager.delete_session(session_id)
    
    def list_sessions(self) -> List[SessionResponse]:
        """
        List all active sessions.
        
        Returns:
            List of session responses.
        """
        sessions = ChatbotSessionManager.list_sessions()
        return [s.to_response() for s in sessions]
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Process a chat message using session configuration.
        
        Args:
            request: Chat request with session ID and message.
            
        Returns:
            Chat response with answer and sources.
            
        Raises:
            ValueError: If session not found.
        """
        # Get session
        session = ChatbotSessionManager.get_session(request.session_id)
        if not session:
            raise ValueError(f"Session not found: {request.session_id}")
        
        logger.info(
            f"Processing chat for session {request.session_id}: "
            f"RAG={session.rag_strategy}, VectorStore={session.vector_store}, "
            f"message_length={len(request.message or '')}, has_image={request.query_image_base64 is not None}"
        )
        
        # Build parameters from session config with optional overrides
        top_k = request.top_k or session.retrieval_config.get("top_k", 10)
        filters = request.filters or session.retrieval_config.get("filters")
        score_threshold = session.retrieval_config.get("score_threshold", 0.0)
        system_prompt = request.system_prompt or session.generation_config.get("system_prompt")
        
        # Execute appropriate RAG strategy
        rag_type = session.rag_strategy.lower()
        vector_store = session.vector_store
        collection_name = session.collection_name
        
        # Call the appropriate RAG service method based on strategy
        if rag_type == "naive":
            result = await self.rag_service.execute_naive_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "advanced":
            rerank = session.retrieval_config.get("rerank", False)
            result = await self.rag_service.execute_advanced_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                rerank=rerank,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "hierarchical":
            num_summaries = session.strategy_config.get("num_summaries", 3)
            result = await self.rag_service.execute_hierarchical_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                num_summaries=num_summaries,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "graph":
            traversal_depth = session.strategy_config.get("traversal_depth", 2)
            relationship_types = session.strategy_config.get("relationship_types")
            result = await self.rag_service.execute_graph_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                traversal_depth=traversal_depth,
                relationship_types=relationship_types,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "agentic":
            max_iterations = session.strategy_config.get("max_iterations", 3)
            result = await self.rag_service.execute_agentic_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                max_iterations=max_iterations,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "hybrid":
            vector_weight = session.strategy_config.get("vector_weight", 0.7)
            result = await self.rag_service.execute_hybrid_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                top_k=top_k,
                filters=filters,
                vector_weight=vector_weight,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        elif rag_type == "conversational":
            memory_window = session.strategy_config.get("memory_window", 5)
            result = await self.rag_service.execute_conversational_rag(
                query=request.message or "",
                vector_store_name=vector_store,
                collection_name=collection_name,
                session_id=request.session_id,
                top_k=top_k,
                filters=filters,
                memory_window=memory_window,
                score_threshold=score_threshold,
                system_prompt=system_prompt,
                query_image_base64=request.query_image_base64
            )
        
        else:
            raise ValueError(f"Unknown RAG strategy: {rag_type}")
        
        # Build response
        sources = [
            SourceDocument(
                id=s.id,
                content=s.content,
                score=s.score,
                metadata=s.metadata,
                source=s.source
            )
            for s in result.sources
        ]
        
        return ChatResponse(
            answer=result.answer,
            sources=sources,
            session_id=request.session_id,
            rag_strategy=result.rag_type,
            vector_store=result.vector_store,
            confidence=result.confidence,
            metadata=result.metadata
        )

