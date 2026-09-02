"""
GraphRAG Strategy

Entity-relationship graph traversal combined with vector search.
"""

import logging
from typing import List, Optional, Dict, Any, Set

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


@register_strategy(RAGType.GRAPH)
class GraphRAG(RAGStrategy):
    """
    GraphRAG implementation combining graph traversal with vector search.
    
    Features:
    - Entity extraction from query
    - Graph neighborhood exploration
    - Relationship-aware retrieval
    - Subgraph context building
    """

    @property
    def rag_type(self) -> RAGType:
        return RAGType.GRAPH

    async def _extract_entities(self, query: str) -> List[str]:
        """
        Extract key entities from the query using LLM.
        """
        try:
            logger.info(f"Extracting entities from query: {query}")
            messages = [
                {"role": "system", "content": """Extract key entities (people, organizations, concepts, products, etc.) from the query.
Return only the entity names, one per line, without explanations or numbering."""},
                {"role": "user", "content": query}
            ]
            
            response = await self.llm.invoke(messages)
            logger.debug(f"LLM response for entity extraction: {response}")
            entities = [
                line.strip()
                for line in response.strip().split("\n")
                if line.strip()
            ]
            
            logger.info(f"Extracted entities: {entities[:5]}")
            return entities[:5]  # Limit to top 5 entities
            
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return []

    async def _find_entity_nodes(
        self,
        entities: List[str],
        context: RetrievalContext
    ) -> List[str]:
        """
        Find nodes in the graph that match the extracted entities.
        """
        try:
            logger.info(f"Finding entity nodes for entities: {entities}")
            matching_ids = []
            
            for entity in entities:
                logger.debug(f"Embedding entity: {entity}")
                entity_embedding = await self.embedder.embed(entity)
                
                logger.debug(f"Querying vector store for entity: {entity}")
                results = await self.vector_store.query(
                    collection_name=context.collection_name,
                    query_vector=entity_embedding,
                    top_k=2,
                    filters=context.filters,
                )
                logger.debug(f"Results for entity '{entity}': {[r.id for r in results]}")
                for r in results:
                    if r.score > 0.7:  # High similarity threshold
                        logger.debug(f"Entity '{entity}' matched node {r.id} with score {r.score}")
                        matching_ids.append(r.id)
            
            deduped = list(set(matching_ids))[:10]
            logger.info(f"Matched entity node ids: {deduped}")
            return deduped  # Deduplicate and limit
            
        except Exception as e:
            logger.error(f"Error finding entity nodes: {e}")
            return []

    async def _traverse_graph(
        self,
        node_ids: List[str],
        context: RetrievalContext,
        depth: int = 2
    ) -> Dict[str, Any]:
        """
        Traverse the graph from starting nodes.
        Requires Neo4j adapter for graph-specific operations.
        """
        try:
            logger.info(f"Traversing graph from node_ids: {node_ids} at depth: {depth}")
            # Check if vector store supports graph operations
            if hasattr(self.vector_store, 'get_subgraph'):
                logger.debug("Using vector_store.get_subgraph for traversal")
                subgraph = await self.vector_store.get_subgraph(
                    collection_name=context.collection_name,
                    node_ids=node_ids,
                    depth=depth,
                )
                logger.info(f"Subgraph retrieved (nodes: {len(subgraph.get('nodes', []))}, relationships: {len(subgraph.get('relationships', []))})")
                logger.debug(f"Subgraph: {subgraph}")
                return subgraph
            
            # Fall back to simple neighbor retrieval
            if hasattr(self.vector_store, 'get_neighbors'):
                logger.debug("Using vector_store.get_neighbors for traversal")
                all_nodes = {}
                relationships = []
                
                visited: Set[str] = set()
                to_visit = list(node_ids)
                
                for d in range(depth):
                    logger.debug(f"Graph traversal depth {d+1}/{depth}, visiting: {to_visit}")
                    next_to_visit = []
                    for node_id in to_visit:
                        if node_id in visited:
                            logger.debug(f"Node {node_id} already visited")
                            continue
                        visited.add(node_id)
                        
                        neighbors = await self.vector_store.get_neighbors(
                            collection_name=context.collection_name,
                            node_id=node_id,
                        )
                        logger.debug(f"Neighbors for node {node_id}: {[n.id for n in neighbors]}")
                        for neighbor in neighbors:
                            all_nodes[neighbor.id] = neighbor
                            relationships.append({
                                "from": node_id,
                                "to": neighbor.id,
                            })
                            if neighbor.id not in visited:
                                next_to_visit.append(neighbor.id)
                    
                    to_visit = next_to_visit
                
                logger.info(f"Traversal complete. Nodes found: {len(all_nodes)}. Relationships: {len(relationships)}")
                return {
                    "nodes": list(all_nodes.values()),
                    "relationships": relationships,
                }
            
            # No graph support - return empty
            logger.warning("Vector store does not support graph operations")
            return {"nodes": [], "relationships": []}
            
        except Exception as e:
            logger.error(f"Error traversing graph: {e}")
            return {"nodes": [], "relationships": []}

    async def retrieve(
        self,
        query: str,
        context: RetrievalContext
    ) -> List[RetrievedDocument]:
        """
        Graph-aware retrieval combining vector search and graph traversal.
        """
        try:
            logger.info(f"Starting retrieval for query: '{query}' with context: {context}")
            documents = []
            
            # Step 1: Standard vector retrieval
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
            logger.debug(f"Query embedding computed for retrieval")
            vector_results = await self.vector_store.query(
                collection_name=context.collection_name,
                query_vector=query_embedding,
                top_k=context.top_k // 2,
                filters=context.filters,
            )
            logger.info(f"Retrieved {len(vector_results)} documents by vector search")
            for r in vector_results:
                logger.debug(f"Vector result: id={r.id} score={r.score}")
                documents.append(RetrievedDocument(
                    id=r.id,
                    content=r.payload.get("content", ""),
                    score=r.score,
                    metadata={**r.payload, "retrieval_method": "vector"},
                    source=r.payload.get("source"),
                ))
            
            # Step 2: Entity-based graph traversal
            entities = await self._extract_entities(query)
            logger.info(f"Entities after extraction: {entities}")
            
            if entities:
                entity_node_ids = await self._find_entity_nodes(entities, context)
                logger.info(f"Entity node ids found: {entity_node_ids}")
                
                if entity_node_ids:
                    traversal_depth = context.metadata.get("traversal_depth", 2)
                    logger.info(f"Traversing subgraph from entity nodes at depth {traversal_depth}")
                    subgraph = await self._traverse_graph(
                        entity_node_ids, context, traversal_depth
                    )
                    
                    # Add graph nodes to documents
                    seen_ids = {d.id for d in documents}
                    logger.debug(f"Already seen document ids: {seen_ids}")
                    nodes_added = 0
                    for node in subgraph.get("nodes", []):
                        if isinstance(node, dict):
                            node_id = node.get("id")
                            if node_id and node_id not in seen_ids:
                                documents.append(RetrievedDocument(
                                    id=node_id,
                                    content=node.get("metadata", {}).get("content", ""),
                                    score=0.5,  # Default score for graph-retrieved
                                    metadata={
                                        **node.get("metadata", {}),
                                        "retrieval_method": "graph",
                                    },
                                    source=node.get("metadata", {}).get("source"),
                                ))
                                seen_ids.add(node_id)
                                logger.debug(f"Added graph node (dict) document {node_id}")
                                nodes_added += 1
                        elif hasattr(node, 'id'):
                            if node.id not in seen_ids:
                                documents.append(RetrievedDocument(
                                    id=node.id,
                                    content=node.payload.get("content", ""),
                                    score=0.5,
                                    metadata={
                                        **node.payload,
                                        "retrieval_method": "graph",
                                    },
                                    source=node.payload.get("source"),
                                ))
                                seen_ids.add(node.id)
                                logger.debug(f"Added graph node document {node.id}")
                                nodes_added += 1
                    logger.info(f"Added {nodes_added} nodes from graph traversal to documents")
            
            # Sort by score and limit
            documents.sort(key=lambda x: x.score, reverse=True)
            documents = documents[:context.top_k]
            
            logger.info(f"GraphRAG retrieved {len(documents)} documents total (after sorting & limiting)")
            return documents
            
        except Exception as e:
            logger.error(f"Error in graph retrieval: {e}")
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
        Generate answer with graph-aware context and multimodal image support.
        Supports multimodal input by including images from retrieved documents and query images.
        """
        try:
            logger.info(f"Generating output for query: '{query}'. Number of documents: {len(documents)}")
            
            # Separate image and text documents first
            image_documents, text_documents = self._separate_image_documents(documents)
            logger.debug(f"Found {len(image_documents)} image documents and {len(text_documents)} text documents")
            
            # Check if query image is provided
            has_query_image = (query_image_base64 and query_image_base64.strip()) or (query_image_bytes and len(query_image_bytes) > 0)
            logger.debug(f"Query image provided: {has_query_image}")
            
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
            
            # Separate text documents by retrieval method
            vector_docs = [d for d in text_documents if d.metadata.get("retrieval_method") == "vector"]
            graph_docs = [d for d in text_documents if d.metadata.get("retrieval_method") == "graph"]
            logger.debug(f"Vector docs count: {len(vector_docs)}, Graph docs count: {len(graph_docs)}")
            
            # Build structured context from text documents
            context_parts = []
            
            if vector_docs:
                context_parts.append("## Directly Relevant Documents:")
                for i, doc in enumerate(vector_docs, 1):
                    context_parts.append(f"[Doc {i}]: {doc.content}")
            else:
                logger.info("No directly relevant documents were found by vector retrieval.")

            if graph_docs:
                context_parts.append("\n## Related Context (via entity relationships):")
                for i, doc in enumerate(graph_docs, 1):
                    context_parts.append(f"[Related {i}]: {doc.content}")
            else:
                logger.info("No related context documents found via graph traversal.")
            
            context = "\n".join(context_parts) if context_parts else ""
            logger.debug(f"Built context for generation: {context}")
            
            sys_prompt = system_prompt or """You are an assistant that answers questions using both direct document matches, related context discovered through entity relationships, and images.

Instructions:
- Primary answers should come from "Directly Relevant Documents"
- "Related Context" provides additional background and connections
- For images, describe what you see and cite them appropriately
- Explain relationships between concepts when relevant
- Cite your sources using [Doc N] or [Related N] notation"""
            
            # Build prompt text with enhanced image-only query support
            if context:
                prompt_text = f"""{context}

Question: {query}

Provide a comprehensive answer that leverages both direct and related context:"""
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

Provide a comprehensive answer:"""
                        else:
                            prompt_text = f"""Answer the following question about the image provided below.

Question: {query}

Provide a comprehensive answer:"""
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
            logger.debug(f"Invoking LLM for answer generation with {len(image_content)} images.")
            response = await self.llm.invoke(messages)
            logger.info("LLM response generation completed.")
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
        Execute the full GraphRAG pipeline.
        """
        logger.info(f"Executing GraphRAG pipeline. Query: '{query}'. Config: {config}")
        retrieval_context = RetrievalContext(
            collection_name=config.collection_name,
            top_k=config.top_k,
            filters=config.filters,
            score_threshold=config.score_threshold,
            metadata={
                "traversal_depth": config.extra_params.get("traversal_depth", 2),
            },
            query_text=query,
            query_image_base64=config.extra_params.get("query_image_base64"),
            query_image_bytes=config.extra_params.get("query_image_bytes"),
        )
        
        logger.debug(f"RetrievalContext constructed: {retrieval_context}")
        documents = await self.retrieve(query, retrieval_context)
        logger.info(f"Retrieved {len(documents)} documents for final response assembly.")

        answer = await self.generate(
            query=query,
            documents=documents,
            system_prompt=config.system_prompt,
        )
        logger.info("Generated answer for query response.")
        
        confidence = self._calculate_confidence(documents)
        logger.info(f"Calculated confidence: {confidence}")
        
        # Count retrieval methods
        vector_count = sum(1 for d in documents if d.metadata.get("retrieval_method") == "vector")
        graph_count = sum(1 for d in documents if d.metadata.get("retrieval_method") == "graph")
        logger.debug(f"Vector retrieved: {vector_count}, Graph retrieved: {graph_count}")
        
        logger.info("Returning RAGResponse object from GraphRAG pipeline.")
        return RAGResponse(
            answer=answer,
            sources=self._documents_to_sources(documents),
            rag_type=self.rag_type.value,
            vector_store=config.vector_store,
            confidence=confidence,
            metadata={
                "total_documents": len(documents),
                "vector_retrieved": vector_count,
                "graph_retrieved": graph_count,
            }
        )

