"""RAG feature settings (vector stores, ingestion defaults, Textract)."""

from typing import Optional

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    """Settings owned by the RAG feature package."""

    # ============== Database (PostgreSQL / pgvector) ==============
    POSTGRES_SERVER: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_USER: str = Field(default="postgres")
    POSTGRES_PASSWORD: str = Field(default="")
    POSTGRES_DB: str = Field(default="rag_boilerplate")
    POSTGRES_SCHEMA: Optional[str] = Field(
        default=None,
        description="PostgreSQL schema name for pgvector tables.",
    )

    # ============== AWS Textract ==============
    TEXTRACT_REGION: Optional[str] = Field(
        default=None, description="AWS region for Textract (defaults to AWS_REGION)"
    )
    TEXTRACT_S3_BUCKET: Optional[str] = Field(
        default=None, description="S3 bucket for async Textract operations"
    )

    # ============== Qdrant ==============
    QDRANT_URL: str = Field(default="http://localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_API_KEY: Optional[str] = Field(default=None)

    # ============== Milvus ==============
    MILVUS_URI: Optional[str] = Field(
        default=None,
        description="Milvus Cloud URI. If set, takes precedence over MILVUS_HOST/PORT.",
    )
    MILVUS_HOST: str = Field(default="localhost")
    MILVUS_PORT: int = Field(default=19530)
    MILVUS_TOKEN: Optional[str] = Field(default=None)

    # ============== OpenSearch ==============
    OPENSEARCH_HOST: str = Field(default="localhost")
    OPENSEARCH_PORT: int = Field(default=9200)
    OPENSEARCH_USER: str = Field(default="admin")
    OPENSEARCH_PASSWORD: Optional[str] = Field(default=None)
    OPENSEARCH_USE_SSL: bool = Field(default=True)

    # ============== Neo4j ==============
    NEO4J_URI: Optional[str] = Field(
        default=None,
        description="Neo4j AuraDB URI. If set, takes precedence over NEO4J_HOST/PORT.",
    )
    NEO4J_HOST: str = Field(default="localhost")
    NEO4J_PORT: int = Field(default=7687)
    NEO4J_USER: str = Field(default="neo4j")
    NEO4J_PASSWORD: Optional[str] = Field(default=None)

    # ============== FAISS ==============
    FAISS_STORAGE_PATH: str = Field(default="./faiss_data")

    # ============== AWS OpenSearch ==============
    AWS_OPENSEARCH_ENDPOINT: str = Field(default="")
    AWS_OPENSEARCH_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None)
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None)

    # ============== Default RAG Settings ==============
    DEFAULT_VECTOR_STORE: str = Field(default="qdrant")
    DEFAULT_RAG_TYPE: str = Field(default="naive")
    DEFAULT_TOP_K: int = Field(default=10)
    DEFAULT_SCORE_THRESHOLD: float = Field(default=0.0)
    DEFAULT_VECTOR_DIM: int = Field(default=1536)
    DEFAULT_CHUNK_SIZE: int = Field(default=1000)
    DEFAULT_CHUNK_OVERLAP: int = Field(default=200)

    # Multimodal embedding stays on the feature (gateway has text-only parity)
    BEDROCK_MULTIMODAL_EMBEDDING_MODEL_ID: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "BEDROCK_MULTIMODAL_EMBEDDING_MODEL_ID",
            "MULTIMODAL_EMBEDDING_MODEL_ID",
        ),
        description="Multimodal embedding model ID (image / text+image).",
    )

    # Legacy app name fields (optional)
    APP_NAME: str = Field(default="Knowledge Augmentation Framework")
    DEBUG: bool = Field(default=False)

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        """Build async PostgreSQL connection string (lazy; no import-time DB connect)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def SYNC_DATABASE_URI(self) -> str:
        """Build sync PostgreSQL connection string (for migrations)."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


def get_vector_store_config(store_type: str) -> dict:
    """
    Get configuration dict for a specific vector store type.

    Lazy: reads settings only when called; does not connect to any DB.
    """
    from app.config.settings import settings

    configs = {
        "qdrant": {
            "url": settings.QDRANT_URL,
            "port": settings.QDRANT_PORT,
            "api_key": settings.QDRANT_API_KEY,
        },
        "milvus": {
            "host": settings.MILVUS_HOST,
            "port": settings.MILVUS_PORT,
            "token": settings.MILVUS_TOKEN,
            "uri": settings.MILVUS_URI,
        },
        "pgvector": {
            "host": settings.POSTGRES_SERVER,
            "port": settings.POSTGRES_PORT,
            "user": settings.POSTGRES_USER,
            "password": settings.POSTGRES_PASSWORD,
            "database": settings.POSTGRES_DB,
            "schema": settings.POSTGRES_SCHEMA,
        },
        "opensearch": {
            "host": settings.OPENSEARCH_HOST,
            "port": settings.OPENSEARCH_PORT,
            "user": settings.OPENSEARCH_USER,
            "password": settings.OPENSEARCH_PASSWORD,
            "use_ssl": settings.OPENSEARCH_USE_SSL,
        },
        "aws_opensearch": {
            "endpoint": settings.AWS_OPENSEARCH_ENDPOINT,
            "region": settings.AWS_OPENSEARCH_REGION,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
        },
        "faiss": {
            "storage_path": settings.FAISS_STORAGE_PATH,
        },
        "neo4j": {
            "host": settings.NEO4J_HOST,
            "port": settings.NEO4J_PORT,
            "user": settings.NEO4J_USER,
            "password": settings.NEO4J_PASSWORD,
            "uri": settings.NEO4J_URI,
        },
    }

    if store_type not in configs:
        raise ValueError(f"Unknown vector store type: {store_type}")

    return configs[store_type]
