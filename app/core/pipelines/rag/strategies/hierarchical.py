"""
Hierarchical RAG Strategy

Multi-level document retrieval from summaries to details.
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

logger = logging.getLogger(__name__)


@register_strategy(RAGType.HIERARCHICAL)
class HierarchicalRAG(RAGStrategy):
    """
    Hierarchical RAG implementation with multi-level retrieval.
    
    Features:
    - Document summaries at parent level
    - Detailed chunks at child level
    - Summary-guided retrieval
    - Context expansion from summaries to details
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.HIERARCHICAL

    async def _retrieve_summaries(
        self,
        query: str,
        context: RetrievalContext,
        top_k: int = 5
    ) -> List[RetrievedDocument]:
        """
        First-level retrieval: get relevant document summaries.
        """
        try:
            logger.info(f"[HierarchicalRAG] Retrieving summaries for query: '{query}' (top_k={top_k}) in collection '{context.collection_name}'")
            # Check if multimodal query
            is_multimodal = (
                context.query_image_base64 is not None or 
                context.query_image_bytes is not None
            )
            if is_multimodal and hasattr(self.embedder, 'embed_multimodal'):
                query_embedding = await self.embedder.embed_multimodal(
                    text=query if query else None,
                    image_base64=context.query_image_base64,
                    image_bytes=context.query_image_bytes
                )
            else:
                query_embedding = await self.embedder.embed(query)
            
            # Query summary collection (convention: {collection}_summaries)
            summary_collection = f"{context.collection_name}_summaries"
            logger.debug(f"[HierarchicalRAG] Trying summary collection: '{summary_collection}'")
            
            # Check if summary collection exists
            if not await self.vector_store.collection_exists(summary_collection):
                logger.info(f"[HierarchicalRAG] Summary collection '{summary_collection}' does not exist. Falling back to main collection '{context.collection_name}'")
                summary_collection = context.collection_name
            
            results = await self.vector_store.query(
                collection_name=summary_collection,
                query_vector=query_embedding,
                top_k=top_k,
                filters=context.filters,
            )
            logger.info(f"[HierarchicalRAG] Retrieved {len(results)} summary results from collection '{summary_collection}'")
            summary_docs = [
                RetrievedDocument(
                    id=r.id,
                    content=r.payload.get("summary", r.payload.get("content", "")),
                    score=r.score,
                    metadata=r.payload,
                    source=r.payload.get("source"),
                )
                for r in results
            ]
            logger.debug(f"[HierarchicalRAG] Summary doc IDs: {[d.id for d in summary_docs]}")
            return summary_docs
            
        except Exception as e:
            logger.error(f"Error retrieving summaries: {e}", exc_info=True)
            return []

    async def _retrieve_children(
        self,
        parent_ids: List[str],
        context: RetrievalContext,
        query: str
    ) -> List[RetrievedDocument]:
        """
        Second-level retrieval: get detailed chunks for parent documents.
        """
        try:
            logger.info(f"[HierarchicalRAG] Retrieving children for parent_ids: {parent_ids} (total={len(parent_ids)})")
            all_children = []
            # Check if multimodal query
            is_multimodal = (
                context.query_image_base64 is not None or 
                context.query_image_bytes is not None
            )
            if is_multimodal and hasattr(self.embedder, 'embed_multimodal'):
                query_embedding = await self.embedder.embed_multimodal(
                    text=query if query else None,
                    image_base64=context.query_image_base64,
                    image_bytes=context.query_image_bytes
                )
            else:
                query_embedding = await self.embedder.embed(query)
            
            # Get children for each parent
            for parent_id in parent_ids:
                logger.debug(f"[HierarchicalRAG] Querying for children with parent_id: {parent_id}")
                # Filter for children of this parent
                child_filters = {
                    **(context.filters or {}),
                    "parent_id": parent_id,
                }
                
                results = await self.vector_store.query(
                    collection_name=context.collection_name,
                    query_vector=query_embedding,
                    top_k=context.top_k // len(parent_ids) + 1,
                    filters=child_filters,
                )
                logger.debug(f"[HierarchicalRAG] Retrieved {len(results)} child results for parent_id: {parent_id}")
                for r in results:
                    all_children.append(
                        RetrievedDocument(
                            id=r.id,
                            content=r.payload.get("content", ""),
                            score=r.score,
                            metadata={**r.payload, "parent_id": parent_id},
                            source=r.payload.get("source"),
                        )
                    )
            
            # Sort all children by score and return top_k
            all_children.sort(key=lambda x: x.score, reverse=True)
            logger.info(f"[HierarchicalRAG] Total collected children before truncation: {len(all_children)}. Returning top {context.top_k}")
            return all_children[:context.top_k]
            
        except Exception as e:
            logger.error(f"Error retrieving children: {e}", exc_info=True)
            return []

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Two-stage hierarchical retrieval.
        """
        try:
            logger.info(f"[HierarchicalRAG] Beginning hierarchical retrieval for query: '{query}' with RetrievalContext: {context}")
            # Stage 1: Retrieve summaries
            num_summaries = context.metadata.get("num_summaries", 3)
            summaries = await self._retrieve_summaries(query, context, num_summaries)
            
            if not summaries:
                # Fall back to direct retrieval
                logger.warning("No summaries found, falling back to direct retrieval")
                # Check if multimodal query
                is_multimodal = (
                    context.query_image_base64 is not None or 
                    context.query_image_bytes is not None
                )
                if is_multimodal and hasattr(self.embedder, 'embed_multimodal'):
                    query_embedding = await self.embedder.embed_multimodal(
                        text=query if query else None,
                        image_base64=context.query_image_base64,
                        image_bytes=context.query_image_bytes
                    )
                else:
                    query_embedding = await self.embedder.embed(query)
                logger.info(f"[HierarchicalRAG] Direct retrieval from collection: '{context.collection_name}' with top_k={context.top_k}")
                results = await self.vector_store.query(
                    collection_name=context.collection_name,
                    query_vector=query_embedding,
                    top_k=context.top_k,
                    filters=context.filters,
                )
                direct_docs = [
                    RetrievedDocument(
                        id=r.id,
                        content=r.payload.get("content", ""),
                        score=r.score,
                        metadata=r.payload,
                        source=r.payload.get("source"),
                    )
                    for r in results
                ]
                logger.info(f"[HierarchicalRAG] Directly retrieved {len(direct_docs)} documents")
                return direct_docs
            
            logger.info(f"[HierarchicalRAG] Retrieved {len(summaries)} summaries for Stage 2 child retrieval")
            # Stage 2: Retrieve children from top summaries
            parent_ids = [s.id for s in summaries]
            children = await self._retrieve_children(parent_ids, context, query)
            
            # Combine summaries and children, prioritizing children
            documents = children
            
            # Add summaries as context if we don't have enough children
            if len(documents) < context.top_k:
                logger.info(f"[HierarchicalRAG] Not enough children retrieved ({len(documents)}/{context.top_k}), supplementing with summaries")
                for summary in summaries:
                    if len(documents) >= context.top_k:
                        break
                    # Add summary if not already present
                    if summary.id not in [d.metadata.get("parent_id") for d in documents]:
                        documents.append(summary)
                        logger.debug(f"[HierarchicalRAG] Added summary {summary.id} to fill result set")
            
            logger.info(f"Hierarchical retrieval: {len(summaries)} summaries, {len(children)} children, {len(documents)} final documents")
            return documents
            
        except Exception as e:
            logger.error(f"Error in hierarchical retrieval: {e}", exc_info=True)
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
        Generate answer with hierarchical context awareness and multimodal image support.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        try:
            logger.info(f"[HierarchicalRAG] Generating response for query: '{query}' with {len(documents)} retrieved documents")
            
            # Separate image and text documents
            image_documents, text_documents = self._separate_image_documents(documents)
            logger.debug(f"[HierarchicalRAG] Found {len(image_documents)} image documents and {len(text_documents)} text documents")
            
            # Check if query image is provided
            has_query_image = (query_image_base64 and query_image_base64.strip()) or (query_image_bytes and len(query_image_bytes) > 0)
            logger.debug(f"[HierarchicalRAG] Query image provided: {has_query_image}")
            
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
                    logger.debug(f"[HierarchicalRAG] Added query image to message (mime_type: {mime_type}, base64_len: {len(image_base64)})")
            
            # Add images from retrieved documents
            user_content.extend(image_content)
            
            # Organize text documents by parent
            parent_children: Dict[str, List[RetrievedDocument]] = {}
            standalone = []
            
            for doc in text_documents:
                parent_id = doc.metadata.get("parent_id")
                if parent_id:
                    if parent_id not in parent_children:
                        parent_children[parent_id] = []
                    parent_children[parent_id].append(doc)
                else:
                    standalone.append(doc)
            
            logger.debug(f"[HierarchicalRAG] Count of parent groups: {len(parent_children)}, standalone docs: {len(standalone)}")

            # Build structured context from text documents
            context_parts = []
            
            # Add parent-children groups
            for i, (parent_id, children) in enumerate(parent_children.items(), 1):
                context_parts.append(f"## Document Group {i}")
                for j, child in enumerate(children, 1):
                    context_parts.append(f"### Section {j}:\n{child.content}")
                context_parts.append("")
            
            # Add standalone documents
            for i, doc in enumerate(standalone, 1):
                context_parts.append(f"## Document {i}:\n{doc.content}")
            
            context = "\n".join(context_parts) if context_parts else ""
            logger.debug(f"[HierarchicalRAG] Context for LLM prompt: {context[:300]}...")  # Only show first 300 chars
            
            sys_prompt = system_prompt or """You are a helpful assistant that answers questions using hierarchical document context and images.

Instructions:
- The context is organized hierarchically with document groups and sections.
- For images, describe what you see and cite them appropriately.
- Synthesize information from multiple sections when relevant.
- Reference specific sections when citing information.
- If the context doesn't contain enough information, say so clearly."""
            
            # Build prompt text with enhanced image-only query support
            if context:
                prompt_text = f"""Based on the following hierarchical context, answer the question.

{context}

Question: {query}

Answer:"""
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

Answer:"""
                        else:
                            prompt_text = f"""Answer the following question about the image provided below.

Question: {query}

Answer:"""
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
            
            logger.info(f"[HierarchicalRAG] Invoking LLM for answer generation with {len(image_content)} images.")
            response = await self.llm.invoke(messages)
            logger.info(f"[HierarchicalRAG] LLM response length: {len(response) if response else 'None'}")
            return response
            
        except Exception as e:
            logger.error(f"Error in generation: {e}", exc_info=True)
            return f"I encountered an error generating a response: {str(e)}"

    async def execute(
        self,
        query: str,
        config: RAGConfig
    ) -> RAGResponse:
        """
        Execute the full Hierarchical RAG pipeline.
        """
        logger.info(f"[HierarchicalRAG] Executing pipeline for query: '{query}' with config: {config}")
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            score_threshold=config.score_threshold,
            metadata=config.extra_params,
            query_text=query,
            query_image_base64=config.extra_params.get("query_image_base64"),
            query_image_bytes=config.extra_params.get("query_image_bytes"),
        )
        
        documents = await self.retrieve(query, retrieval_context)
        logger.info(f"[HierarchicalRAG] Retrieved {len(documents)} documents for answer generation")
        
        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
        )
        
        confidence = self._calculate_confidence(documents)
        logger.info(f"[HierarchicalRAG] Pipeline output: confidence={confidence}, vector_store={config.vector_store}")
        
        return RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "hierarchical_levels": 2,
            }
        )

