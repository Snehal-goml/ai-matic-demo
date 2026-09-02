"""
Qdrant Vector Store Adapter

This module provides the Qdrant implementation of the VectorStoreAdapter interface.
"""

import uuid
import logging
import time
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
    Filter,
    FieldCondition,
    MatchValue,
    MatchAny,
    ScrollRequest,
)

from app.adapters.vector_store.base import (
    VectorStoreAdapter,
    VectorStoreConfig,
    SearchResult,
    DistanceMetric,
)
from app.config.rag.registry import register_adapter

logger = logging.getLogger(__name__)


def _map_distance_metric(metric: DistanceMetric) -> Distance:
    """Map our distance metric to Qdrant's Distance enum."""
    mapping = {
        DistanceMetric.COSINE: Distance.COSINE,
        DistanceMetric.EUCLIDEAN: Distance.EUCLID,
        DistanceMetric.DOT_PRODUCT: Distance.DOT,
    }
    logger.debug(f"Mapping distance metric '{metric}' to Qdrant Distance enum.")
    return mapping.get(metric, Distance.COSINE)


def _build_qdrant_filter(filters: Dict[str, Any]) -> Optional[Filter]:
    """Convert filter dict to Qdrant Filter object."""
    if not filters:
        logger.debug("No filters provided for Qdrant query.")
        return None
    
    conditions = []
    for key, value in filters.items():
        # Skip None, empty dict, or empty list values
        if value is None or value == {} or value == []:
            logger.debug(f"Skipping filter key '{key}' with empty/None value: {value}")
            continue
        
        # Handle different value types
        if isinstance(value, (str, int, float, bool)):
            logger.debug(f"Adding filter condition: field={key}, value={value}")
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )
        elif isinstance(value, list):
            # Handle list values (IN operator)
            if len(value) > 0:
                # Qdrant supports MatchAny for list values
                conditions.append(
                    FieldCondition(key=key, match=MatchAny(any=value))
                )
        else:
            logger.warning(f"Unsupported filter value type for key '{key}': {type(value)}, value: {value}")
            continue
    
    if not conditions:
        logger.debug("No valid filter conditions generated from given filters.")
        return None
    
    logger.debug(f"Created Qdrant Filter with {len(conditions)} conditions.")
    return Filter(must=conditions)


@register_adapter("qdrant")
class QdrantAdapter(VectorStoreAdapter):
    """
    Qdrant vector database adapter.
    
    Qdrant is a high-performance vector similarity search engine
    with advanced filtering capabilities.
    """

    def __init__(self, config: VectorStoreConfig):
        """Initialize the Qdrant adapter."""
        super().__init__(config)
        self._client: Optional[QdrantClient] = None
        logger.debug(f"QdrantAdapter initialized with config: host={self.config.host}, port={self.config.port}")

    async def connect(self) -> None:
        """Establish connection to Qdrant."""
        try:
            # Extract Qdrant-specific config
            api_key = self.config.api_key
            prefer_grpc = self.config.extra_params.get("prefer_grpc", False)
            timeout = self.config.extra_params.get("timeout", 30)
            logger.debug(f"Connecting to Qdrant at {self.config.host}:{self.config.port}, grpc={prefer_grpc}, timeout={timeout}")

            self._client = QdrantClient(
                url=self.config.host if "://" in self.config.host else f"http://{self.config.host}",
                port=self.config.port,
                api_key=api_key,
                prefer_grpc=prefer_grpc,
                timeout=timeout,
            )
            logger.info(f"Connected to Qdrant at {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            raise ConnectionError(f"Failed to connect to Qdrant: {e}")

    async def disconnect(self) -> None:
        """Close connection to Qdrant."""
        if self._client:
            logger.debug("Closing Qdrant client connection.")
            self._client.close()
            self._client = None
            logger.info("Disconnected from Qdrant")
        else:
            logger.debug("No Qdrant client to disconnect.")

    async def create_collection(
        self,
        collection_name: str,
        vector_dim: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        **kwargs
    ) -> bool:
        """Create a new collection in Qdrant."""
        logger.info(f"Attempting to create Qdrant collection '{collection_name}' with dimension={vector_dim}, distance_metric={distance_metric}")
        try:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_dim,
                    distance=_map_distance_metric(distance_metric),
                ),
            )
            logger.info(f"Created Qdrant collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create collection {collection_name}: {e}")
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection from Qdrant."""
        logger.info(f"Attempting to delete Qdrant collection '{collection_name}'")
        try:
            self._client.delete_collection(collection_name=collection_name)
            logger.info(f"Deleted Qdrant collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False

    def _to_qdrant_id(self, id_str: str):
        """
        Convert any string ID to a valid Qdrant ID (UUID or integer).
        Qdrant requires IDs to be either non-negative integers or UUIDs.
        We hash the original ID to generate a deterministic UUID.
        """
        import hashlib
        
        # Try to parse as integer first
        try:
            int_id = int(id_str)
            if int_id >= 0:  # Qdrant accepts non-negative integers
                return int_id
        except (ValueError, TypeError):
            pass
        
        # Try to parse as UUID
        try:
            uuid.UUID(id_str)
            return id_str  # Already a valid UUID
        except (ValueError, TypeError):
            pass
        
        # Convert string to UUID by hashing
        # Use MD5 to generate a deterministic UUID v3-style hash
        hash_obj = hashlib.md5(id_str.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()
        # Format as UUID
        qdrant_uuid = f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
        logger.debug(f"Converted ID '{id_str[:50]}...' to Qdrant UUID: {qdrant_uuid}")
        return qdrant_uuid

    async def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists in Qdrant."""
        logger.debug(f"Checking existence of Qdrant collection: '{collection_name}'")
        try:
            exists = self._client.collection_exists(collection_name)
            logger.info(f"Collection '{collection_name}' existence: {exists}")
            return exists
        except Exception as e:
            logger.error(f"Error checking collection existence: {e}")
            return False

    async def upsert(
        self,
        collection_name: str,
        ids: List[str],
        embeddings: List[List[float]],
        metadata: List[Dict[str, Any]],
        **kwargs
    ) -> int:
        """Insert or update vectors in Qdrant."""
        logger.info(f"Upserting {len(ids)} vectors into collection '{collection_name}'")
        try:
            points = []
            for id_val, embedding, meta in zip(ids, embeddings, metadata):
                # IDs are now UUIDs, so convert to Qdrant-compatible format
                # Qdrant accepts UUIDs as strings, so we can use them directly
                qdrant_id = self._to_qdrant_id(str(id_val))
                
                points.append(
                    PointStruct(
                        id=qdrant_id,
                        vector=embedding,
                        payload=meta,
                    )
                )

            # Batch upsert for large datasets
            batch_size = kwargs.get("batch_size", 100)
            total_upserted = 0

            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                logger.debug(f"Upserting batch {i // batch_size + 1} with {len(batch)} vectors into '{collection_name}'")
                self._client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )
                total_upserted += len(batch)
                logger.debug(f"Upserted batch {i // batch_size + 1}: {len(batch)} vectors")

            logger.info(f"Upserted {total_upserted} vectors to {collection_name}")
            return total_upserted
        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            return 0

    async def query(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_vectors: bool = False,
        **kwargs
    ) -> List[SearchResult]:
        """Query Qdrant for similar vectors."""
        logger.info(f"Querying Qdrant collection '{collection_name}' for top {top_k} similar vectors")
        logger.debug(f"Query vector (first 5 dims): {query_vector[:5]}... | Filters: {filters} | include_vectors={include_vectors}")
        try:
            if not self._client:
                logger.error("Qdrant client not connected")
                return []
            
            score_threshold = kwargs.get("score_threshold", None)
            if score_threshold is not None:
                logger.debug(f"Using score_threshold: {score_threshold}")
            
            # Qdrant client methods are synchronous, so we need to run them in a thread
            import asyncio
            
            def _search():
                """Synchronous search function to run in thread."""
                # Use query_points method (correct API for qdrant-client)
                # The query parameter can be a vector (list) or a Query object
                query_filter = _build_qdrant_filter(filters)
                
                search_results = self._client.query_points(
                    collection_name=collection_name,
                    query=query_vector,  # Can be a list of floats
                    limit=top_k,
                    query_filter=query_filter,
                    score_threshold=score_threshold,
                    with_vectors=include_vectors,
                )
                
                # The response is a QueryResponse object with a 'points' attribute
                if hasattr(search_results, 'points'):
                    return search_results.points
                elif isinstance(search_results, list):
                    return search_results
                else:
                    # Try to get points from the response object
                    return getattr(search_results, 'points', [])
            
            # Run synchronous search in thread pool
            results = await asyncio.to_thread(_search)

            search_results = []
            for result in results:
                payload = result.payload or {}
                # IDs are now UUIDs, use Qdrant ID directly (it's already a UUID)
                search_results.append(
                    SearchResult(
                        id=str(result.id),
                        score=result.score,
                        payload=payload,
                        vector=result.vector if include_vectors else None,
                    )
                )

            logger.info(f"Query on collection '{collection_name}' returned {len(search_results)} results")
            return search_results
        except Exception as e:
            logger.error(f"Failed to query vectors: {e}")
            return []

    async def delete(
        self,
        collection_name: str,
        ids: List[str]
    ) -> bool:
        """Delete vectors by ID from Qdrant."""
        logger.info(f"Deleting {len(ids)} vectors from collection '{collection_name}'")
        try:
            # Convert IDs to Qdrant format
            qdrant_ids = [self._to_qdrant_id(str(id_val)) for id_val in ids]
            
            self._client.delete(
                collection_name=collection_name,
                points_selector=qdrant_ids,
            )
            logger.info(f"Deleted {len(ids)} vectors from {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete vectors: {e}", exc_info=True)
            return False

    async def get_by_ids(
        self,
        collection_name: str,
        ids: List[str],
        include_vectors: bool = False
    ) -> List[SearchResult]:
        """Retrieve vectors by ID from Qdrant."""
        logger.info(f"Retrieving {len(ids)} vectors by ID from collection '{collection_name}' (include_vectors={include_vectors})")
        try:
            # Convert IDs to Qdrant format
            qdrant_ids = [self._to_qdrant_id(str(id_val)) for id_val in ids]
            
            results = self._client.retrieve(
                collection_name=collection_name,
                ids=qdrant_ids,
                with_vectors=include_vectors,
            )

            logger.debug(f"Retrieved {len(results)} vectors by ID from collection '{collection_name}'")
            search_results = []
            for result in results:
                payload = result.payload or {}
                # IDs are now UUIDs, use Qdrant ID directly
                search_results.append(
                    SearchResult(
                        id=str(result.id),
                        score=1.0,  # Retrieved by ID, no score
                        payload=payload,
                        vector=result.vector if include_vectors else None,
                    )
                )
            return search_results
        except Exception as e:
            logger.error(f"Failed to retrieve vectors by ID: {e}", exc_info=True)
            return []

    async def count(self, collection_name: str) -> int:
        """Get the number of vectors in a collection."""
        logger.info(f"Getting point count for Qdrant collection '{collection_name}'")
        try:
            collection_info = self._client.get_collection(collection_name)
            logger.debug(f"Collection '{collection_name}' has {collection_info.points_count} points")
            return collection_info.points_count
        except Exception as e:
            logger.error(f"Failed to get collection count: {e}")
            return 0

    async def health_check(self) -> bool:
        """Check if Qdrant is healthy."""
        logger.info("Performing Qdrant health check by listing collections")
        try:
            # Simple health check by listing collections
            self._client.get_collections()
            logger.debug("Qdrant health check passed")
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
