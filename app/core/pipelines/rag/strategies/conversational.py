"""
Conversational RAG Strategy

Memory-aware RAG with conversation history support.
"""

import logging
from typing import List, Optional, Dict, Any

from app.core.pipelines.rag.base import (
    RAGStrategy,
    RAGConfig,
    RAGResponse,
    RAGType,
    RetrievedDocument,
    RetrievalContext,
)
from app.config.rag.registry import register_strategy
from app.config.rag.session import SessionManager, ConversationMessage

logger = logging.getLogger(__name__)


@register_strategy(RAGType.CONVERSATIONAL)
class ConversationalRAG(RAGStrategy):
    """
    Conversational RAG implementation with memory and context awareness.
    
    Features:
    - Conversation history tracking
    - Context-aware query rewriting
    - Coreference resolution
    - Follow-up question handling
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.CONVERSATIONAL

    async def _rewrite_query_with_context(
        self,
        query: str,
        conversation_history: List[ConversationMessage],
        window_size: int = 5
    ) -> str:
        """
        Rewrite the query to include context from conversation history.
        Resolves pronouns and references to previous messages.
        """
        if not conversation_history:
            logger.debug("[_rewrite_query_with_context] No conversation history, returning original query.")
            return query
        
        try:
            # Get recent messages
            recent_messages = conversation_history[-window_size:]
            logger.debug(f"[_rewrite_query_with_context] Using last {window_size} messages for query rewriting.")

            # Build conversation context
            conv_context = "\n".join([
                f"{msg.role.capitalize()}: {msg.content}"
                for msg in recent_messages
            ])
            logger.debug(f"[_rewrite_query_with_context] Conversation context built:\n{conv_context}")

            messages = [
                {"role": "system", "content": """You are a query rewriter. Given a conversation history and a new query, rewrite the query to be self-contained.

Rules:
- Replace pronouns (it, they, this, that) with their referents from the conversation
- Include relevant context from the conversation
- Keep the rewritten query concise but complete
- If the query is already self-contained, return it unchanged
- Return ONLY the rewritten query, nothing else."""},
                {"role": "user", "content": f"""Conversation history:
{conv_context}

New query: {query}

Rewritten query:"""}
            ]
            
            logger.info("[_rewrite_query_with_context] Invoking LLM for query rewriting.")
            response = await self.llm.invoke(messages)
            rewritten = response.strip()
            
            logger.info(f"[_rewrite_query_with_context] Original query: '{query}' | Rewritten query: '{rewritten}'")
            logger.debug(f"[_rewrite_query_with_context] LLM raw response: {response}")
            return rewritten
            
        except Exception as e:
            logger.warning(f"Query rewriting failed: {e}")
            return query

    async def _get_conversation_context(
        self,
        session_id: str,
        window_size: int
    ) -> List[ConversationMessage]:
        """
        Get relevant conversation history for context.
        """
        try:
            logger.debug(f"[_get_conversation_context] Getting conversation context for session_id={session_id}, window_size={window_size}")
            conversation = SessionManager.get_conversation(session_id)
            context_window = conversation.get_context_window(window_size)
            logger.debug(f"[_get_conversation_context] Retrieved {len(context_window)} messages from session {session_id}")
            return context_window
        except Exception as e:
            logger.warning(f"Failed to get conversation context: {e}")
            return []

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Context-aware retrieval using conversation history.
        """
        try:
            logger.info(f"[retrieve] Starting conversational retrieval for query: '{query}' with context: {context}")
            # Get conversation history if session_id is provided
            session_id = context.metadata.get("session_id")
            window_size = context.metadata.get("memory_window", 5)
            
            # Get conversation history
            conv_history = []
            if session_id:
                logger.debug(f"[retrieve] Fetching conversation history for session_id={session_id}, window_size={window_size}")
                conv_history = await self._get_conversation_context(
                    session_id, window_size
                )
            else:
                logger.debug("[retrieve] No session_id provided, skipping conversation history.")

            # Rewrite query with conversation context
            logger.debug(f"[retrieve] Rewriting query with context. Original query: '{query}'")
            effective_query = await self._rewrite_query_with_context(
                query, conv_history, window_size
            )
            
            logger.info(f"[retrieve] Effective query after rewriting: '{effective_query}'")

            # Embed the rewritten query
            logger.debug("[retrieve] Embedding effective query.")
            # Check if multimodal query
            is_multimodal = (
                context.query_image_base64 is not None or 
                context.query_image_bytes is not None
            )
            if is_multimodal and hasattr(self.embedder, 'embed_multimodal'):
                # For multimodal, use original query with image
                query_embedding = await self.embedder.embed_multimodal(
                    text=effective_query if effective_query else None,
                    image_base64=context.query_image_base64,
                    image_bytes=context.query_image_bytes
                )
            else:
                query_embedding = await self.embedder.embed(effective_query)
            
            # Search
            logger.info(f"[retrieve] Querying vector store '{context.collection_name}' with top_k={context.top_k}")
            results = await self.vector_store.query(
                collection_name=context.collection_name,
                query_vector=query_embedding,
                top_k=context.top_k,
                filters=context.filters,
            )
            
            documents = [
                RetrievedDocument(
                    id=r.id,
                    content=r.payload.get("content", str(r.payload)),
                    score=r.score,
                    metadata={
                        **r.payload,
                        "original_query": query,
                        "effective_query": effective_query,
                    },
                    source=r.payload.get("source"),
                )
                for r in results
            ]
            
            logger.info(f"Conversational retrieval: {len(documents)} documents retrieved for query '{query}'")
            return documents
            
        except Exception as e:
            logger.error(f"Error in conversational retrieval: {e}")
            return []

    async def generate(
        self,
        query: str,
        documents: List[RetrievedDocument],
        system_prompt: Optional[str] = None,
        query_image_base64: Optional[str] = None,
        query_image_bytes: Optional[bytes] = None,
        **kwargs
    ) -> str:
        """
        Generate response with conversation awareness and multimodal image support.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        try:
            logger.debug(f"[generate] Generating response for query: '{query}' with {len(documents)} retrieved documents.")
            
            # Separate image and text documents
            image_documents, text_documents = self._separate_image_documents(documents)
            logger.debug(f"[generate] Found {len(image_documents)} image documents and {len(text_documents)} text documents")
            
            # Check if query image is provided
            has_query_image = (query_image_base64 and query_image_base64.strip()) or (query_image_bytes and len(query_image_bytes) > 0)
            logger.debug(f"[generate] Query image provided: {has_query_image}")
            
            # Build text context from text documents
            text_context = self._build_context(text_documents) if text_documents else ""
            
            # Build image content blocks from retrieved documents
            image_content = self._build_image_content_blocks(image_documents)
            
            # Build message content - support multimodal for Claude 3
            user_content = []
            
            # Add query image first if provided
            if has_query_image:
                image_base64 = query_image_base64 if query_image_base64 and query_image_base64.strip() else None
                if not image_base64 and query_image_bytes:
                    import base64
                    image_base64 = base64.b64encode(query_image_bytes).decode('utf-8')
                
                if image_base64:
                    # Try to detect image format from base64 header or default to PNG
                    mime_type = self._detect_image_mime_type(query_image_bytes) if query_image_bytes else "image/png"
                    
                    user_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_base64
                        }
                    })
                    logger.debug(f"[generate] Added query image to message (mime_type: {mime_type}, base64_len: {len(image_base64)})")
            
            # Add images from retrieved documents
            user_content.extend(image_content)
            
            # Get conversation history
            session_id = kwargs.get("session_id")
            conversation_history = []
            if session_id:
                logger.debug(f"[generate] Fetching conversation history for session_id={session_id}, window_size={kwargs.get('memory_window', 5)}")
                conversation_history = await self._get_conversation_context(
                    session_id,
                    kwargs.get("memory_window", 5)
                )
            
            # Build conversation messages for LLM
            sys_prompt = system_prompt or """You are a helpful conversational assistant that answers questions based on the provided context and images.

Instructions:
- Consider the conversation history when formulating your response.
- For images, describe what you see and cite them appropriately.
- Maintain consistency with previous answers.
- Reference previous points in the conversation when relevant.
- If asked for clarification or follow-up, refer back to your previous responses.
- Always ground your answers in the provided context documents.
- If you don't have enough information, say so clearly."""
            
            # Build messages with conversation history
            messages = [{"role": "system", "content": sys_prompt}]
            
            # Add conversation history
            for msg in conversation_history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            # Add current turn with context
            effective_query = query
            if documents and documents[0].metadata.get("effective_query"):
                effective_query = documents[0].metadata["effective_query"]
            logger.debug(f"[generate] Using effective_query: '{effective_query}'")

            # Build prompt text with enhanced image-only query support
            if text_context:
                prompt_text = f"""[Retrieved Context]
{text_context}

[Current Question]
{query}

Please provide a helpful response:"""
            else:
                if has_query_image or image_documents:
                    # Enhanced prompt for image queries
                    if not query or query.strip() == "":
                        # Image-only query - provide detailed analysis
                        if image_documents:
                            prompt_text = """[Current Question]
Please analyze the images provided below. For each image, provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

If multiple images are provided, describe each one separately and clearly distinguish between them. Be specific and accurate in your descriptions."""
                        else:
                            # Only query image, no retrieved images
                            prompt_text = """[Current Question]
Please analyze the image provided below. Provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

Be specific and accurate in your description."""
                    else:
                        # Text query with images
                        if image_documents:
                            prompt_text = f"""[Current Question]
Answer the following question about the image(s) provided below. 

When describing images, be specific and accurate. If multiple images are shown, clearly identify which image you're referring to.

{query}

Please provide a helpful response:"""
                        else:
                            prompt_text = f"""[Current Question]
{query}

Please provide a helpful response about the image provided:"""
                else:
                    prompt_text = f"""[Current Question]
{query}

I couldn't find any relevant documents in the knowledge base to answer your question. You may want to try rephrasing your question or checking if the relevant information has been ingested into the system."""
            
            # Build multimodal content
            if user_content or has_query_image or image_documents:
                # If we have images, add text as part of the content list
                user_content.append({"type": "text", "text": prompt_text})
            else:
                # If no images, just use text string
                user_content = prompt_text

            messages.append({
                "role": "user",
                "content": user_content
            })
            
            logger.info(f"[generate] Invoking LLM to generate response.")
            response = await self.llm.invoke(messages)
            logger.debug(f"[generate] LLM response generated.")

            # Store this interaction in conversation history
            if session_id:
                try:
                    logger.debug(f"[generate] Storing interaction to conversation history for session_id={session_id}")
                    conversation = SessionManager.get_conversation(session_id)
                    conversation.add_message("user", query)
                    conversation.add_message("assistant", response)
                except Exception as e:
                    logger.warning(f"[generate] Failed to store conversation history: {e}")
            
            logger.info(f"[generate] Generation completed for query '{query}'")
            return response
            
        except Exception as e:
            logger.error(f"Error in generation: {e}")
            return f"I encountered an error generating a response: {str(e)}"

    async def execute(
        self,
        query: str,
        config: RAGConfig
    ) -> RAGResponse:
        """
        Execute the full Conversational RAG pipeline.
        """
        logger.info(f"[execute] Initiating Conversational RAG for query: '{query}' in collection: '{config.collection_name}'")
        session_id = config.extra_params.get("session_id")
        memory_window = config.extra_params.get("memory_window", 5)
        
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            score_threshold=config.score_threshold,
            metadata={
                "session_id": session_id,
                "memory_window": memory_window,
            },
            query_text=query,
            query_image_base64=config.extra_params.get("query_image_base64"),
            query_image_bytes=config.extra_params.get("query_image_bytes"),
        )
        
        logger.debug(f"[execute] Retrieval context: {retrieval_context}")

        documents = await self.retrieve(query, retrieval_context)
        
        logger.debug(f"[execute] Retrieved {len(documents)} documents. Proceeding to generate response.")
        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
            session_id=session_id,
            memory_window=memory_window,
        )
        
        confidence = self._calculate_confidence(documents)
        logger.debug(f"[execute] Calculated confidence score: {confidence}")

        # Get effective query if rewritten
        effective_query = query
        if documents and documents[0].metadata.get("effective_query"):
            effective_query = documents[0].metadata["effective_query"]
        logger.info(f"[execute] Effective query used: '{effective_query}' | Query rewritten: {query != effective_query}")

        response = RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "session_id": session_id,
                "query_rewritten": query != effective_query,
                "effective_query": effective_query if query != effective_query else None,
            }
        )

        logger.info(f"[execute] Conversational RAG pipeline complete for query: '{query}'. Returning response.")
        return response

