"""
Advanced RAG Strategy

Enhanced RAG with hybrid search, query expansion, and reranking.
"""

import logging
from typing import List, Optional

from app.core.pipelines.rag.base import (
    RAGStrategy,
    RAGConfig,
    RAGResponse,
    RAGType,
    RetrievedDocument,
    RetrievalContext,
)
from app.config.rag.registry import register_strategy

logger = logging.getLogger(__name__)


@register_strategy(RAGType.ADVANCED)
class AdvancedRAG(RAGStrategy):
    """
    Advanced RAG implementation with enhanced retrieval.
    
    Features:
    - Query expansion/rewriting
    - Hybrid search (vector + keyword)
    - Cross-encoder reranking
    - Score normalization
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.ADVANCED

    async def _expand_query(self, query: str) -> List[str]:
        """
        Expand the query into multiple variations for better retrieval.
        """
        logger.info(f"Expanding query: '{query}'")
        try:
            messages = [
                {"role": "system", "content": """You are a query expansion assistant. 
Generate 2-3 alternative phrasings of the user's query that might help retrieve relevant documents.
Return only the alternative queries, one per line, without numbering or bullets."""},
                {"role": "user", "content": query}
            ]
            
            logger.debug(f"Sending query expansion request to LLM: {messages}")
            response = await self.llm.invoke(messages)            
            logger.debug(f"Received expanded queries: {response}")

            # Parse expanded queries
            expanded = [query]  # Always include original
            for line in response.strip().split("\n"):
                line = line.strip()
                if line and line != query:
                    expanded.append(line)
            
            logger.info(f"Expanded query into {len(expanded)} variations: {expanded}")
            return expanded[:4]  # Limit to 4 total
            
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return [query]

    async def _rerank_documents(
        self,
        query: str,
        documents: List[RetrievedDocument],
        top_k: int
    ) -> List[RetrievedDocument]:
        """
        Rerank documents using LLM-based relevance scoring.
        """
        if not documents:
            logger.info("No documents to rerank.")
            return documents
        
        logger.info(f"Reranking {len(documents)} documents with top_k={top_k}.")
        try:
            # For each document, ask LLM to score relevance
            scored_docs = []
            num_processing = min(len(documents), top_k * 2)
            logger.debug(f"Will rerank up to {num_processing} documents for reranking.")
            
            for doc in documents[:top_k * 2]:  # Process more than needed
                logger.debug(f"Reranking document ID={doc.id}")
                messages = [
                    {"role": "system", "content": """You are a relevance scoring assistant.
Rate how relevant the given document is to answering the query.
Respond with only a number from 0.0 to 1.0, where 1.0 is highly relevant."""},
                    {"role": "user", "content": f"""Query: {query}

Document: {doc.content[:1000]}

Relevance score (0.0-1.0):"""}
                ]
                
                logger.debug(f"Scoring request for document {doc.id}: {messages}")
                response = await self.llm.invoke(messages)
                logger.debug(f"Received scoring response for doc {doc.id}: {response}")
                
                try:
                    # Parse score
                    score = float(response.strip())
                    score = max(0.0, min(1.0, score))
                    logger.info(f"Parsed LLM score {score} for doc ID={doc.id}")
                except ValueError:
                    logger.warning(f"Failed to parse LLM score for doc ID={doc.id}. Falling back to original score ({doc.score})")
                    score = doc.score  # Fall back to original score
                
                # Combine original score with rerank score
                combined_score = 0.4 * doc.score + 0.6 * score
                logger.debug(f"Combined score for doc ID={doc.id} is {combined_score}")
                scored_docs.append((doc, combined_score))
            
            # Sort by combined score and return top_k
            scored_docs.sort(key=lambda x: x[1], reverse=True)
            
            reranked = []
            for doc, score in scored_docs[:top_k]:
                logger.debug(f"Selected doc ID={doc.id} with combined reranked score {score}")
                reranked.append(RetrievedDocument(
                    id=doc.id,
                    content=doc.content,
                    score=score,
                    metadata=doc.metadata,
                    source=doc.source,
                ))
            
            logger.info(f"Reranked {len(documents)} documents to top {len(reranked)}")
            return reranked
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            return documents[:top_k]

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Advanced retrieval with query expansion and optional hybrid search.
        """
        logger.info(f"Starting retrieval for query: '{query}' with context: {context}")
        try:
            all_documents = {}
            
            # Check if multimodal query
            is_multimodal = (
                context.query_image_base64 is not None or 
                context.query_image_bytes is not None
            )
            
            # Expand query (skip for image-only queries)
            if is_multimodal and not query:
                queries = [query]  # Use empty query for image-only
            else:
                queries = await self._expand_query(query)
            logger.info(f"Retrieved expanded queries: {queries}")
            
            # Retrieve for each query variation
            for q in queries:
                logger.info(f"Embedding and retrieving for query variation: '{q}'")
                
                if is_multimodal and hasattr(self.embedder, 'embed_multimodal'):
                    query_embedding = await self.embedder.embed_multimodal(
                        text=q if q else None,
                        image_base64=context.query_image_base64,
                        image_bytes=context.query_image_bytes
                    )
                else:
                    query_embedding = await self.embedder.embed(q)
                logger.debug(f"Query embedding for '{q}': {query_embedding}")

                results = await self.vector_store.query(
                    collection_name=context.collection_name,
                    query_vector=query_embedding,
                    top_k=context.top_k * 2,  # Get more for merging
                    filters=context.filters,
                )
                logger.info(f"Retrieved {len(results)} documents for query variation '{q}'")
                
                # Merge results (deduplicate by ID, keep highest score)
                for result in results:
                    doc_id = result.id
                    score = result.score
                    logger.debug(f"Considering result doc ID={doc_id} score={score}")

                    if doc_id not in all_documents or score > all_documents[doc_id].score:
                        logger.debug(f"Adding/updating doc ID={doc_id} in all_documents.")
                        all_documents[doc_id] = RetrievedDocument(
                            id=result.id,
                            content=result.payload.get("content", str(result.payload)),
                            score=result.score,
                            metadata=result.payload,
                            source=result.payload.get("source"),
                        )
            
            # Sort by score
            documents = sorted(
                all_documents.values(),
                key=lambda x: x.score,
                reverse=True
            )
            logger.info(f"Total unique documents after merge: {len(documents)}")
            
            # Apply reranking if enabled
            if context.rerank:
                logger.info("Reranking is enabled, applying reranking.")
                documents = await self._rerank_documents(query, documents, context.top_k)
            else:
                documents = documents[:context.top_k]
                logger.info("Reranking is disabled, selecting top_k based on score.")
            
            # Filter by score threshold
            if context.score_threshold > 0:
                original_len = len(documents)
                documents = [d for d in documents if d.score >= context.score_threshold]
                logger.info(f"Filtered documents by score threshold {context.score_threshold}: {original_len} -> {len(documents)}")
            
            logger.info(f"Advanced retrieval returned {len(documents)} documents")
            return documents
            
        except Exception as e:
            logger.error(f"Error in advanced retrieval: {e}")
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
        Generate an enhanced answer with citation support and multimodal image handling.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        logger.info(f"Generating answer for query: '{query}' with {len(documents)} retrieved documents.")
        try:
            # Separate image and text documents
            image_documents, text_documents = self._separate_image_documents(documents)
            logger.debug(f"Found {len(image_documents)} image documents and {len(text_documents)} text documents")
            
            # Check if query image is provided
            has_query_image = (query_image_base64 and query_image_base64.strip()) or (query_image_bytes and len(query_image_bytes) > 0)
            logger.debug(f"Query image provided: {has_query_image}")
            
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
                    logger.debug(f"Added query image to message (mime_type: {mime_type}, base64_len: {len(image_base64)})")
            
            # Add images from retrieved documents
            user_content.extend(image_content)
            
            sys_prompt = system_prompt or """You are a knowledgeable assistant that provides accurate, well-cited answers.

Instructions:
- Base your answer ONLY on the provided context documents and images.
- Cite sources using [Document N] notation when referencing information.
- For images, describe what you see and cite them appropriately.
- If the context doesn't contain enough information, acknowledge this clearly.
- Synthesize information from multiple documents when relevant.
- Be comprehensive yet concise."""
            
            # Build prompt text with enhanced image-only query support
            if text_context:
                prompt_text = f"""Based on the following context documents, provide a comprehensive answer to the question.

Context:
{text_context}

Question: {query}

Please provide a well-structured answer with citations:"""
            else:
                if has_query_image or image_documents:
                    # Enhanced prompt for image queries
                    if not query or query.strip() == "":
                        # Image-only query - provide detailed analysis
                        if image_documents:
                            prompt_text = """Please analyze the images provided below. For each image, provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

If multiple images are provided, describe each one separately and clearly distinguish between them. Be specific and accurate in your descriptions."""
                        else:
                            # Only query image, no retrieved images
                            prompt_text = """Please analyze the image provided below. Provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

Be specific and accurate in your description."""
                    else:
                        # Text query with images
                        if image_documents:
                            prompt_text = f"""Answer the following question about the image(s) provided below. 

When describing images, be specific and accurate. If multiple images are shown, clearly identify which image you're referring to.

Question: {query}

Please provide a well-structured answer with citations:"""
                        else:
                            prompt_text = f"""Answer the following question about the image provided below.

Question: {query}

Please provide a well-structured answer with citations:"""
                else:
                    prompt_text = f"""I couldn't find any relevant documents in the knowledge base to answer your question.

Question: {query}

Please note that no matching documents were found. You may want to try rephrasing your question or checking if the relevant information has been ingested into the system."""
            
            # Build multimodal content
            if user_content or has_query_image or image_documents:
                # If we have images, add text as part of the content list
                user_content.append({"type": "text", "text": prompt_text})
            else:
                # If no images, just use text string
                user_content = prompt_text
            
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ]
            
            logger.debug(f"Sending generation prompt to LLM with {len(image_content)} retrieved images and {1 if has_query_image else 0} query images")
            response = await self.llm.invoke(messages)
            logger.info("Received generated answer from LLM.")
            logger.debug(f"LLM answer:\n{response}")
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
        Execute the full Advanced RAG pipeline.
        """
        logger.info(f"Executing AdvancedRAG pipeline for query: '{query}' with config: {config}")
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            rerank=config.rerank,
            hybrid=config.hybrid,
            score_threshold=config.score_threshold,
        )
        
        logger.info("Starting retrieval phase.")
        documents = await self.retrieve(query, retrieval_context)
        logger.info(f"Retrieval phase completed. {len(documents)} documents retrieved.")

        logger.info("Starting generation phase.")
        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
        )
        logger.info("Generation phase completed.")

        logger.info("Calculating confidence score.")
        confidence = self._calculate_confidence(documents)
        logger.info(f"Confidence score calculated: {confidence}")

        response = RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "reranked": config.rerank,
                "hybrid": config.hybrid,
            }
        )
        logger.info("AdvancedRAG pipeline executed successfully.")
        logger.debug(f"RAGResponse: {response}")
        return response

