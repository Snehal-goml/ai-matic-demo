"""
Agentic RAG Strategy

LLM-controlled retrieval with planning, tool use, and self-reflection.
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass

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


class AgentAction(Enum):
    """Actions the agent can take."""
    SEARCH = "search"
    REFINE_QUERY = "refine_query"
    EXPAND_CONTEXT = "expand_context"
    SYNTHESIZE = "synthesize"
    FINISH = "finish"


@dataclass
class AgentState:
    """State maintained by the agent during execution."""
    query: str
    retrieved_documents: List[RetrievedDocument]
    search_queries: List[str]
    iterations: int
    max_iterations: int
    is_sufficient: bool
    reasoning: List[str]


@register_strategy(RAGType.AGENTIC)
class AgenticRAG(RAGStrategy):
    """
    Agentic RAG implementation with LLM-controlled retrieval.
    
    Features:
    - Query planning and decomposition
    - Iterative retrieval with reflection
    - Self-assessment of context sufficiency
    - Multi-step reasoning
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.AGENTIC

    async def _plan_queries(self, query: str) -> List[str]:
        """
        Decompose the query into sub-queries for comprehensive retrieval.
        """
        try:
            logger.info(f"[PlanQueries] Starting planning for query: {query}")
            messages = [
                {"role": "system", "content": """You are a query planning assistant.
Break down the user's question into 1-3 specific sub-queries that would help retrieve comprehensive information.
Return only the queries, one per line, without numbering or explanations.
If the query is simple, return just the original query."""},
                {"role": "user", "content": query}
            ]
            
            response = await self.llm.invoke(messages)
            logger.debug(f"[PlanQueries] LLM response: {response}")

            queries = [query]  # Always include original
            for line in response.strip().split("\n"):
                line = line.strip()
                if line and line not in queries:
                    queries.append(line)
            
            logger.info(f"[PlanQueries] Planned {len(queries)} queries: {queries}")
            return queries[:4]
            
        except Exception as e:
            logger.warning(f"[PlanQueries] Query planning failed: {e}")
            return [query]

    async def _assess_sufficiency(
        self,
        query: str,
        documents: List[RetrievedDocument]
    ) -> Dict[str, Any]:
        """
        Assess whether the retrieved context is sufficient to answer the query.
        """
        try:
            logger.info(f"[AssessSufficiency] Assessing context for query: {query}, {len(documents)} documents")
            if not documents:
                logger.info("[AssessSufficiency] No documents retrieved, returning insufficient")
                return {"sufficient": False, "reason": "No documents retrieved"}
            
            context = self._build_context(documents[:5])  # Check top 5
            logger.debug(f"[AssessSufficiency] Built context for LLM: {context}")

            messages = [
                {"role": "system", "content": """You are evaluating whether the provided context is sufficient to answer a question.
                
Respond in this exact format:
SUFFICIENT: yes/no
REASON: <brief explanation>
MISSING: <what information is missing, if any>"""},
                {"role": "user", "content": f"""Question: {query}

Context:
{context}

Evaluate if this context is sufficient to provide a complete, accurate answer:"""}
            ]
            
            response = await self.llm.invoke(messages)
            logger.debug(f"[AssessSufficiency] LLM response: {response}")

            # Parse response
            lines = response.strip().split("\n")
            sufficient = False
            reason = "Unknown"
            missing = ""
            
            for line in lines:
                if line.upper().startswith("SUFFICIENT:"):
                    sufficient = "yes" in line.lower()
                elif line.upper().startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()
                elif line.upper().startswith("MISSING:"):
                    missing = line.split(":", 1)[1].strip()
            
            logger.info(f"[AssessSufficiency] Result - sufficient: {sufficient}, reason: {reason}, missing: {missing}")
            return {
                "sufficient": sufficient,
                "reason": reason,
                "missing": missing,
            }
            
        except Exception as e:
            logger.warning(f"[AssessSufficiency] Sufficiency assessment failed: {e}")
            return {"sufficient": True, "reason": "Assessment failed, proceeding"}

    async def _refine_query(
        self,
        original_query: str,
        retrieved_docs: List[RetrievedDocument],
        missing_info: str
    ) -> str:
        """
        Refine the query based on what's missing from retrieved context.
        """
        try:
            logger.info(f"[RefineQuery] Refining query '{original_query}' with missing info: {missing_info}")
            messages = [
                {"role": "system", "content": """Based on what information is missing, generate a refined search query.
Return only the new query, without explanation."""},
                {"role": "user", "content": f"""Original question: {original_query}
Missing information: {missing_info}

Generate a refined query to find the missing information:"""}
            ]
            
            response = await self.llm.invoke(messages)
            refined_query = response.strip()
            logger.info(f"[RefineQuery] Refined query: {refined_query}")
            return refined_query
            
        except Exception as e:
            logger.warning(f"[RefineQuery] Query refinement failed: {e}")
            return original_query

    async def _single_retrieval(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Perform a single retrieval operation.
        """
        try:
            logger.info(f"[SingleRetrieval] Starting retrieval for query: {query}")
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
            logger.debug(f"[SingleRetrieval] Got embedding for query.")

            results = await self.vector_store.query(
                collection_name=context.collection_name,
                query_vector=query_embedding,
                top_k=context.top_k,
                filters=context.filters,
            )
            logger.info(f"[SingleRetrieval] Retrieved {len(results)} documents for query: {query}")
            
            docs = [
                RetrievedDocument(
                    id=r.id,
                    content=r.payload.get("content", str(r.payload)),
                    score=r.score,
                    metadata={**r.payload, "search_query": query},
                    source=r.payload.get("source"),
                )
                for r in results
            ]
            logger.debug(f"[SingleRetrieval] Built {len(docs)} RetrievedDocument objects")
            return docs
            
        except Exception as e:
            logger.error(f"[SingleRetrieval] Retrieval failed: {e}")
            return []

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Agentic retrieval with iterative refinement.
        """
        try:
            logger.info(f"[Retrieve] Starting agentic retrieve for query: {query}")
            max_iterations = context.metadata.get("max_iterations", 3)
            
            # Initialize state
            state = AgentState(
                query=query,
                retrieved_documents=[],
                search_queries=[],
                iterations=0,
                max_iterations=max_iterations,
                is_sufficient=False,
                reasoning=[],
            )
            
            # Step 1: Plan queries
            planned_queries = await self._plan_queries(query)
            state.reasoning.append(f"Planned {len(planned_queries)} queries: {planned_queries}")
            logger.info(f"[Retrieve] Planned queries: {planned_queries}")
            
            # Step 2: Initial retrieval with all planned queries
            all_docs = {}
            for q in planned_queries:
                state.search_queries.append(q)
                logger.info(f"[Retrieve] Performing single retrieval with query: {q}")
                docs = await self._single_retrieval(q, context)
                logger.debug(f"[Retrieve] Got {len(docs)} documents for query: {q}")
                for doc in docs:
                    if doc.id not in all_docs or doc.score > all_docs[doc.id].score:
                        all_docs[doc.id] = doc
            
            state.retrieved_documents = sorted(
                all_docs.values(),
                key=lambda x: x.score,
                reverse=True
            )[:context.top_k * 2]  # Keep extra for refinement
            
            state.reasoning.append(f"Initial retrieval: {len(state.retrieved_documents)} documents")
            logger.info(f"[Retrieve] Initial retrieval: {len(state.retrieved_documents)} documents")
            
            # Step 3: Iterative refinement
            while state.iterations < max_iterations:
                state.iterations += 1
                logger.info(f"[Retrieve] Iteration {state.iterations} of {max_iterations}")
                
                # Assess sufficiency
                assessment = await self._assess_sufficiency(
                    query, state.retrieved_documents
                )
                logger.info(f"[Retrieve] Assessment: {assessment}")

                if assessment["sufficient"]:
                    state.is_sufficient = True
                    state.reasoning.append(f"Iteration {state.iterations}: Context sufficient")
                    logger.info(f"[Retrieve] Context sufficient at iteration {state.iterations}")
                    break
                
                state.reasoning.append(
                    f"Iteration {state.iterations}: {assessment['reason']}"
                )
                logger.info(f"[Retrieve] Iteration {state.iterations}: {assessment['reason']}")
                
                # Refine query and retrieve more
                if assessment.get("missing"):
                    refined_query = await self._refine_query(
                        query,
                        state.retrieved_documents,
                        assessment["missing"]
                    )
                    
                    logger.info(f"[Retrieve] Refined query: {refined_query}")

                    if refined_query not in state.search_queries:
                        state.search_queries.append(refined_query)
                        new_docs = await self._single_retrieval(refined_query, context)
                        logger.info(f"[Retrieve] Retrieved {len(new_docs)} new docs using refined query.")
                        
                        # Merge new documents
                        for doc in new_docs:
                            if doc.id not in all_docs:
                                all_docs[doc.id] = doc
                        
                        state.retrieved_documents = sorted(
                            all_docs.values(),
                            key=lambda x: x.score,
                            reverse=True
                        )[:context.top_k * 2]
            
            # Final selection
            final_docs = state.retrieved_documents[:context.top_k]
            
            logger.info(
                f"[Retrieve] Agentic retrieval: {state.iterations} iterations, "
                f"{len(state.search_queries)} queries, "
                f"{len(final_docs)} final documents"
            )
            
            # Store reasoning in metadata
            for doc in final_docs:
                doc.metadata["agent_reasoning"] = state.reasoning
            
            logger.debug(f"[Retrieve] Returning {len(final_docs)} documents")
            return final_docs
            
        except Exception as e:
            logger.error(f"[Retrieve] Error in agentic retrieval: {e}")
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
        Generate answer with agentic reasoning chain and multimodal image support.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        try:
            logger.info(f"[Generate] Generating answer for query: {query}, using {len(documents)} documents")
            
            # Separate image and text documents
            image_documents, text_documents = self._separate_image_documents(documents)
            logger.debug(f"[Generate] Found {len(image_documents)} image documents and {len(text_documents)} text documents")
            
            # Check if query image is provided
            has_query_image = (query_image_base64 and query_image_base64.strip()) or (query_image_bytes and len(query_image_bytes) > 0)
            logger.debug(f"[Generate] Query image provided: {has_query_image}")
            
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
                    logger.debug(f"[Generate] Added query image to message (mime_type: {mime_type}, base64_len: {len(image_base64)})")
            
            # Add images from retrieved documents
            user_content.extend(image_content)
            
            # Get agent reasoning if available
            reasoning = []
            if documents and documents[0].metadata.get("agent_reasoning"):
                reasoning = documents[0].metadata["agent_reasoning"]
                logger.debug(f"[Generate] Found agent reasoning: {reasoning}")
            
            sys_prompt = system_prompt or """You are an intelligent assistant that provides comprehensive answers through careful reasoning.

Instructions:
- Analyze the provided context and images thoroughly
- For images, describe what you see and cite them appropriately
- Explain your reasoning process
- Cite specific documents when making claims
- If information is incomplete, acknowledge limitations
- Provide a clear, well-structured answer"""
            
            # Build prompt with reasoning context
            reasoning_context = ""
            if reasoning:
                reasoning_context = f"""
Retrieval Process:
{chr(10).join(f"- {r}" for r in reasoning)}

"""
            
            # Build prompt text with enhanced image-only query support
            if text_context:
                prompt_text = f"""{reasoning_context}Context Documents:
{text_context}

Question: {query}

Provide a comprehensive answer based on the retrieved context:"""
            else:
                if has_query_image or image_documents:
                    # Enhanced prompt for image queries
                    if not query or query.strip() == "":
                        # Image-only query - provide detailed analysis
                        if image_documents:
                            prompt_text = f"""{reasoning_context}Please analyze the images provided below. For each image, provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

If multiple images are provided, describe each one separately and clearly distinguish between them. Be specific and accurate in your descriptions."""
                        else:
                            # Only query image, no retrieved images
                            prompt_text = f"""{reasoning_context}Please analyze the image provided below. Provide:

1. A detailed description of what you see (objects, people, activities, settings, colors, etc.)
2. Any visible text, logos, or branding
3. The context or scene (e.g., sports event, vehicle, nature, etc.)
4. Any notable details or characteristics

Be specific and accurate in your description."""
                    else:
                        # Text query with images
                        if image_documents:
                            prompt_text = f"""{reasoning_context}Answer the following question about the image(s) provided below. 

When describing images, be specific and accurate. If multiple images are shown, clearly identify which image you're referring to.

Question: {query}

Provide a comprehensive answer:"""
                        else:
                            prompt_text = f"""{reasoning_context}Answer the following question about the image provided below.

Question: {query}

Provide a comprehensive answer:"""
                else:
                    prompt_text = f"""{reasoning_context}I couldn't find any relevant documents in the knowledge base to answer your question.

Question: {query}

Please note that no matching documents were found. You may want to try rephrasing your question or checking if the relevant information has been ingested into the system."""
            
            # Build multimodal content
            if user_content or has_query_image or image_documents:
                # If we have images, add text as part of the content list
                user_content.append({"type": "text", "text": prompt_text})
            else:
                # If no images, just use text string
                user_content = prompt_text
            
            logger.debug(f"[Generate] Building messages for LLM with {len(image_content)} images")
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content}
            ]
            
            response = await self.llm.invoke(messages)
            logger.info(f"[Generate] LLM response length: {len(response) if response else 0}")
            return response
            
        except Exception as e:
            logger.error(f"[Generate] Error in generation: {e}")
            return f"I encountered an error generating a response: {str(e)}"

    async def execute(
        self,
        query: str,
        config: RAGConfig
    ) -> RAGResponse:
        """
        Execute the full Agentic RAG pipeline.
        """
        logger.info(f"[Execute] Starting execution for query: {query}")
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            score_threshold=config.score_threshold,
            metadata={
                "max_iterations": config.extra_params.get("max_iterations", 3),
            },
            query_text=query,
            query_image_base64=config.extra_params.get("query_image_base64"),
            query_image_bytes=config.extra_params.get("query_image_bytes"),
        )
        logger.debug(f"[Execute] Built RetrievalContext: {retrieval_context}")

        documents = await self.retrieve(query, retrieval_context)
        logger.info(f"[Execute] Retrieved {len(documents)} documents")

        # Get reasoning from documents
        reasoning = []
        if documents and documents[0].metadata.get("agent_reasoning"):
            reasoning = documents[0].metadata.pop("agent_reasoning", [])
            logger.debug(f"[Execute] Found agent reasoning steps: {reasoning}")
        
        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
        )
        logger.info(f"[Execute] Generated answer. Length: {len(answer)}")

        confidence = self._calculate_confidence(documents)
        logger.debug(f"[Execute] Calculated confidence: {confidence}")

        # Count unique queries used
        queries_used = set()
        for doc in documents:
            if doc.metadata.get("search_query"):
                queries_used.add(doc.metadata["search_query"])

        logger.info(f"[Execute] Returning RAGResponse with {len(queries_used)} distinct queries used")

        return RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "queries_used": len(queries_used),
                "reasoning_steps": reasoning,
            }
        )

