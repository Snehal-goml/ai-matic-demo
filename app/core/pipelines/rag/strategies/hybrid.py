"""
Hybrid RAG Strategy

Combines vector similarity search with keyword/BM25 search.
"""

import logging
import re
from typing import List, Optional, Dict, Any, Set
from collections import Counter

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


@register_strategy(RAGType.HYBRID)
class HybridRAG(RAGStrategy):
    """
    Hybrid RAG implementation combining vector and keyword search.
    
    Features:
    - Vector similarity search
    - Keyword/BM25-style matching
    - Reciprocal rank fusion for result merging
    - Configurable weighting between methods
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.HYBRID

    def _extract_keywords(self, text: str) -> Set[str]:
        """
        Extract significant keywords from text.
        """
        logger.debug(f"Extracting keywords from text: {text[:100]}..." if len(text) > 100 else f"Extracting keywords from text: {text}")
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each',
            'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
            'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
        }
        
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        keywords = {w for w in words if w not in stop_words}
        logger.debug(f"Extracted keywords: {keywords}")
        return keywords

    def _calculate_keyword_score(
        self,
        query_keywords: Set[str],
        doc_content: str
    ) -> float:
        """
        Calculate a simple keyword matching score.
        """
        logger.debug(f"Calculating keyword score for query_keywords={query_keywords} and doc_content: {doc_content[:100]}..." if len(doc_content) > 100 else f"Calculating keyword score for query_keywords={query_keywords} and doc_content: {doc_content}")
        if not query_keywords:
            logger.debug("No query keywords, returning 0.0 for keyword score.")
            return 0.0
        
        doc_keywords = self._extract_keywords(doc_content)
        
        if not doc_keywords:
            logger.debug("No document keywords, returning 0.0 for keyword score.")
            return 0.0
        
        matches = query_keywords.intersection(doc_keywords)
        coverage = len(matches) / len(query_keywords)
        logger.debug(f"Keyword matching: matches={matches}, coverage={coverage}")
        return coverage

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[RetrievedDocument],
        keyword_results: List[RetrievedDocument],
        k: int = 60,
        vector_weight: float = 0.5
    ) -> List[RetrievedDocument]:
        """
        Merge results using Reciprocal Rank Fusion.
        """
        logger.info(f"Entering reciprocal rank fusion: {len(vector_results)} vector results, {len(keyword_results)} keyword results, k={k}, vector_weight={vector_weight}")
        scores: Dict[str, float] = {}
        doc_map: Dict[str, RetrievedDocument] = {}
        
        keyword_weight = 1.0 - vector_weight
        
        # Score vector results
        for rank, doc in enumerate(vector_results):
            rrf_score = vector_weight * (1.0 / (k + rank + 1))
            scores[doc.id] = scores.get(doc.id, 0) + rrf_score
            doc_map[doc.id] = doc
            logger.debug(f"Vector doc {doc.id} at rank {rank}: RRF score={rrf_score}, total_score={scores[doc.id]}")
        
        # Score keyword results
        for rank, doc in enumerate(keyword_results):
            rrf_score = keyword_weight * (1.0 / (k + rank + 1))
            scores[doc.id] = scores.get(doc.id, 0) + rrf_score
            if doc.id not in doc_map:
                doc_map[doc.id] = doc
            logger.debug(f"Keyword doc {doc.id} at rank {rank}: RRF score={rrf_score}, total_score={scores[doc.id]}")
        
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        logger.debug(f"Documents sorted by fusion score: {sorted_ids}")
        results = []
        for doc_id in sorted_ids:
            doc = doc_map[doc_id]
            results.append(RetrievedDocument(
                id=doc.id,
                content=doc.content,
                score=scores[doc_id],
                metadata={**doc.metadata, "fusion_score": scores[doc_id]},
                source=doc.source,
            ))
        
        logger.info(f"Reciprocal rank fusion complete, returning {len(results)} fused results.")
        return results

    async def _vector_search(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Perform vector similarity search.
        """
        logger.info(f"Starting vector search for query: {query}")
        try:
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
            logger.debug(f"Query embedding generated for vector search.")
            results = await self.vector_store.query(
                collection_name=context.collection_name,
                query_vector=query_embedding,
                top_k=context.top_k * 2,  # Get more for fusion
                filters=context.filters,
            )
            logger.info(f"Vector search returned {len(results)} results for query: {query}")
            return [
                RetrievedDocument(
                    id=r.id,
                    content=r.payload.get("content", str(r.payload)),
                    score=r.score,
                    metadata={**r.payload, "search_method": "vector"},
                    source=r.payload.get("source"),
                )
                for r in results
            ]
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def _keyword_search(
        self,
        query: str,
        context: RetrievalContext,
        all_docs: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """
        Perform keyword-based search.
        For true BM25, would need OpenSearch/Elasticsearch.
        This is a simplified in-memory keyword matching.
        """
        logger.info(f"Starting keyword search for query: {query}, on {len(all_docs)} candidate documents")
        try:
            query_keywords = self._extract_keywords(query)
            
            if not query_keywords:
                logger.warning("No query keywords extracted for keyword search, returning empty results.")
                return []
            
            # Score all documents by keyword match
            scored_docs = []
            for doc in all_docs:
                score = self._calculate_keyword_score(query_keywords, doc.content)
                if score > 0:
                    logger.debug(f"Doc {doc.id} received keyword search score {score}")
                    scored_docs.append(RetrievedDocument(
                        id=doc.id,
                        content=doc.content,
                        score=score,
                        metadata={**doc.metadata, "search_method": "keyword"},
                        source=doc.source,
                    ))
                else:
                    logger.debug(f"Doc {doc.id} received zero keyword score; excluded from keyword search results.")
            
            scored_docs.sort(key=lambda x: x.score, reverse=True)
            logger.info(f"Keyword search finished. Returning {len(scored_docs[:context.top_k * 2])} top results.")
            return scored_docs[:context.top_k * 2]
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Hybrid retrieval combining vector and keyword search.
        """
        logger.info(f"Starting hybrid retrieval for query: {query}")
        try:
            vector_weight = context.metadata.get("vector_weight", 0.7)
            logger.debug(f"Vector weight from context: {vector_weight}")
            
            vector_results = await self._vector_search(query, context)
            logger.info(f"Hybrid retrieval: {len(vector_results)} vector search results retrieved.")

            keyword_results = await self._keyword_search(query, context, vector_results)
            logger.info(f"Hybrid retrieval: {len(keyword_results)} keyword search results retrieved.")

            if context.hybrid and keyword_results:
                logger.info(f"Fusing results with reciprocal rank fusion. Hybrid={context.hybrid}")
                fused_results = self._reciprocal_rank_fusion(
                    vector_results,
                    keyword_results,
                    vector_weight=vector_weight,
                )
            else:
                fused_results = vector_results

            if context.score_threshold > 0:
                num_before = len(fused_results)
                fused_results = [
                    d for d in fused_results
                    if d.score >= context.score_threshold
                ]
                logger.info(f"Score threshold applied: {context.score_threshold}. {num_before} -> {len(fused_results)} results.")

            final_results = fused_results[:context.top_k]
            logger.info(
                f"Hybrid retrieval summary: {len(vector_results)} vector, "
                f"{len(keyword_results)} keyword, "
                f"{len(final_results)} final (vector_weight={vector_weight})"
            )
            
            return final_results
            
        except Exception as e:
            logger.error(f"Error in hybrid retrieval: {e}")
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
        Generate answer from hybrid search results with multimodal image support.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        logger.info(f"Generating answer for query: {query} using {len(documents)} documents.")
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
            
            vector_docs = [d for d in text_documents if d.metadata.get("search_method") == "vector"]
            keyword_docs = [d for d in text_documents if d.metadata.get("search_method") == "keyword"]

            logger.debug(f"Number of vector docs: {len(vector_docs)}, keyword docs: {len(keyword_docs)}")
            
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
            
            sys_prompt = system_prompt or """You are a helpful assistant that answers questions based on the provided context and images.

Instructions:
- The context comes from both semantic similarity and keyword matching.
- For images, describe what you see and cite them appropriately.
- Prioritize information that appears in documents with high relevance scores.
- Cite sources using [Document N] notation.
- If information is conflicting, note the discrepancy."""
            
            # Build prompt text with enhanced image-only query support
            if text_context:
                prompt_text = f"""Context (from hybrid search):
{text_context}

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
            
            logger.debug(f"Sending generation prompt to LLM with {len(image_content)} images")
            response = await self.llm.invoke(messages)
            logger.info(f"Generation complete for query: {query}")
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
        Execute the full Hybrid RAG pipeline.
        """
        logger.info(f"Executing HybridRAG pipeline for query: {query}")
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            hybrid=True,  # Enable hybrid mode
            score_threshold=config.score_threshold,
            metadata={
                "vector_weight": config.extra_params.get("vector_weight", 0.7),
            },
            query_text=query,
            query_image_base64=config.extra_params.get("query_image_base64"),
            query_image_bytes=config.extra_params.get("query_image_bytes"),
        )
        
        documents = await self.retrieve(query, retrieval_context)
        logger.info(f"Retrieved {len(documents)} documents for query: {query}")
        
        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
        )
        logger.info(f"Generated answer for query: {query}")

        confidence = self._calculate_confidence(documents)
        logger.debug(f"Calculated confidence: {confidence}")
        
        vector_count = sum(1 for d in documents if d.metadata.get("search_method") == "vector")
        keyword_count = sum(1 for d in documents if d.metadata.get("search_method") == "keyword")
        logger.info(f"Vector results: {vector_count}, Keyword results: {keyword_count}")
        
        resp = RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "vector_results": vector_count,
                "keyword_results": keyword_count,
                "vector_weight": config.extra_params.get("vector_weight", 0.7),
            }
        )
        logger.info(f"HybridRAG pipeline complete for query: {query}.")
        return resp

