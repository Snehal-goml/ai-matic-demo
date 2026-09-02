"""Configuration owned by the IDP feature."""

from pydantic_settings import BaseSettings


class IDPSettings(BaseSettings):
    BUCKET_NAME: str = ""
    EXTRACTOR_TYPE: str = "AWS_textract"

    MAX_FILE_SIZE_MB: int = 100
    MAX_PAGES_PER_REQUEST: int = 50
    CHUNK_SIZE_MB: int = 10
    MAX_BATCH_FILES: int = 10

    TEXTRACT_TIMEOUT: int = 300
    FILE_UPLOAD_TIMEOUT: int = 120

    MAX_WORKERS: int = 4
    MAX_CONCURRENT_PAGES: int = 5

    S3_PREFIX: str = "document-uploads"
    S3_TEMP_EXPIRY_DAYS: int = 1

    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    ALLOWED_UPLOAD_CONTENT_TYPES: str = ""
    HEALTH_CHECK_S3: bool = False
