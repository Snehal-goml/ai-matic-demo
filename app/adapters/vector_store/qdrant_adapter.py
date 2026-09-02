import uuid
import logging
import yaml
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, Filter
from typing import Dict, Any, List
from app.adapters.embeddings import get_embedder
from app.utils.d2d.vector_utils import extract_payload
from app.config.settings import settings

logger = logging.getLogger(__name__)

class QdrantAdapter:
    """
    QdrantVectorDB provides methods to interact with Qdrant vector database,
    including storing, retrieving, and searching vectorized metadata.
    """

    def __init__(self):
        """
        Initialize the Qdrant client using settings.
        """
        try:
            # Build QdrantClient parameters
            client_params = {
                "api_key": settings.QDRANT_API_KEY,
                "prefer_grpc": False,
                "timeout": 30
            }
            # Only include url if it's provided
            if settings.QDRANT_URL:
                url = settings.QDRANT_URL
                client_params["url"] = url
                
                # Qdrant Cloud usually uses port 443 for HTTPS. 
                # If 'https' is used and no port is specified in the URL, default to 443.
                if url.startswith("https") and ":" not in url.replace("https://", ""):
                    client_params["port"] = 443
                    logger.info("Using port 443 for Qdrant Cloud HTTPS connection.")
            
            self.qdrant = QdrantClient(**client_params)
            logger.info("QdrantClient initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing QdrantClient: {e}")
            raise

    def _collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists (works across qdrant-client versions)."""
        try:
            if hasattr(self.qdrant, "collection_exists"):
                return self.qdrant.collection_exists(collection_name)
            resp = self.qdrant.get_collections()
            colls = getattr(resp, "collections", resp) if not isinstance(resp, list) else resp
            names = [getattr(c, "name", c) for c in colls]
            return collection_name in names
        except Exception:
            return False

    async def ensure_collection_exists(self, collection_name: str, vector_dim: int = 1536):
        """
        Ensure that a Qdrant collection exists. If not, create it.
        Args:
            collection_name: Name of the collection.
            vector_dim: Dimension of the vectors.
        """
        try:
            if not self._collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' does not exist. Creating new collection with vector_dim={vector_dim}.")
                self.qdrant.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
                )
            else:
                logger.info(f"Collection '{collection_name}' already exists.")
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise


    async def store_vectors(self, collection_name: str, enriched_data: Dict[str, Any],
                                vector_dim: int = 1536, reset_collection: bool = True) -> int:
        """
        Store enriched metadata as vectors in Qdrant.
        Args:
            collection_name: Name of the Qdrant collection
            enriched_data: Dictionary of enriched metadata
            vector_dim: Vector dimension (default: 1536 for Titan embeddings)
            reset_collection: If True, deletes the existing collection before inserting
        Returns:
            Number of points stored
        """
        try:
            logger.info(f"Storing vectors for collection '{collection_name}' with {len(enriched_data)} items.")

            # Delete and recreate collection only once if requested
            if reset_collection and self._collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' exists. Deleting for fresh insert.")
                self.qdrant.delete_collection(collection_name=collection_name)

            await self.ensure_collection_exists(collection_name, vector_dim)

            points = []
            for table_name, metadata_text in enriched_data.items():
                # Convert metadata_text to string if it's not already a string
                # This handles cases where YAML upload provides dict values
                if isinstance(metadata_text, str):
                    text_to_embed = metadata_text
                else:
                    # Serialize dict/list to YAML string for embedding
                    text_to_embed = yaml.dump(metadata_text, default_flow_style=False, allow_unicode=True)
                
                payload = {"metadata": metadata_text}
                try:
                    embedder = get_embedder()
                    embedding = await embedder.embed(text_to_embed)
                    if len(embedding) != vector_dim:
                        logger.error(f"Embedding dimension mismatch for table '{table_name}'. Expected {vector_dim}, got {len(embedding)}.")
                        continue
                except Exception as e:
                    logger.error(f"Error embedding text for table '{table_name}': {e}")
                    continue

                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={"table_name": table_name, "metadata": payload}
                )
                points.append(point)

            # Batch insert to handle large data
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                try:
                    self.qdrant.upsert(collection_name=collection_name, points=batch)
                    logger.info(f"Upserted batch {i // batch_size + 1} with {len(batch)} points to collection '{collection_name}'.")
                except Exception as e:
                    logger.error(f"Error upserting batch to Qdrant: {e}")
                    continue

            logger.info(f"Total points stored in collection '{collection_name}': {len(points)}")
            return len(points)

        except Exception as e:
            logger.error(f"Error in store_vectors_dictionary: {e}")
            return 0


    async def retrieve_all_metadata(self, collection_name: str) -> List[Any]:
        """
        Retrieve all metadata from Qdrant.
        Args:
            collection_name: Name of the Qdrant collection.
        Returns:
            List of payloads from all points in the collection.
        """
        try:
            logger.info(f"Retrieving all metadata from collection '{collection_name}'.")
            await self.ensure_collection_exists(collection_name)
            response = self.qdrant.scroll(
                collection_name=collection_name,
                limit=10000
            )
            payloads = [point.payload for point in response[0]]
            logger.info(f"Retrieved {len(payloads)} payloads from collection '{collection_name}'.")
            return payloads
        except Exception as e:
            logger.error(f"Error retrieving all metadata: {e}")
            return []

    async def semantic_search(self, user_query: str, collection_name: str, threshold: float, limit: int = 15) -> List[Any]:
        """
        Retrieve metadata from Qdrant based on semantic similarity to user query.
        Args:
            user_query: The query string to embed and search.
            collection_name: Name of the Qdrant collection.
            threshold: Score threshold for filtering results.
            limit: Maximum number of results to return.
        Returns:
            List of search results (Qdrant points).
        """
        try:
            logger.info(f"Performing semantic search in collection '{collection_name}' for query: {user_query}")
            await self.ensure_collection_exists(collection_name)
            try:
                embedder = get_embedder()
                query_embedding = await embedder.embed(user_query)
            except Exception as e:
                logger.error(f"Error embedding user query: {e}")
                return []
            # Use SearchRequest for vector search (correct API for qdrant-client)
            try:
                from qdrant_client.models import SearchRequest
                search_request = SearchRequest(
                    vector=query_embedding,
                    limit=limit,
                    score_threshold=threshold,
                    with_payload=True
                )
                search_results = self.qdrant.search(
                    collection_name=collection_name,
                    search_request=search_request
                )
            except (ImportError, AttributeError, TypeError) as e:
                # Fallback: Try search with direct parameters (older API)
                logger.warning(f"SearchRequest failed, trying direct search: {e}")
                try:
                    search_results = self.qdrant.search(
                        collection_name=collection_name,
                        query_vector=query_embedding,
                        limit=limit,
                        score_threshold=threshold
                    )
                except AttributeError:
                    # Last fallback: Try query_points if search doesn't exist
                    logger.warning("search method not found, trying query_points")
                    # query_points might work with a different structure
                    query_response = self.qdrant.query_points(
                        collection_name=collection_name,
                        query=query_embedding,
                        limit=limit,
                        score_threshold=threshold
                    )
                    search_results = query_response.points if hasattr(query_response, 'points') else []
            logger.info(f"Semantic search returned {len(search_results)} results for collection '{collection_name}'.")
            return search_results
        except Exception as e:
            logger.error(f"Error in semantic_search: {e}")
            return []

    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a collection from Qdrant.
        Returns True if successful, False otherwise.
        Args:
            collection_name: Name of the Qdrant collection to delete.
        """
        try:
            self.qdrant.delete_collection(collection_name=collection_name)
            logger.info(f"Collection '{collection_name}' deleted successfully.")
            return True
        except Exception as e:
            logger.error(f"Error deleting collection '{collection_name}': {e}")
            return False

# --- Main block for testing semantic_search ---
if __name__ == "__main__":


    # Initialize the vector DB
    vector_db = QdrantAdapter()
    user_query = "Explain what 'Active Living Potential' measures and how it's calculated. What does 0.84 value mean"
    collection_name = "dictionary-metadata"
    print(f"\nSemantic search for query: '{user_query}'")
    results = vector_db.semantic_search(user_query, collection_name, threshold=0.05, limit=10)
    for idx, res in enumerate(results):
        payload = getattr(res, "payload", None)
        score = getattr(res, "score", None)
        print(f"Result {idx+1}:")
        print(f"  Score: {score}")
        print(f"  Payload: {payload}")
