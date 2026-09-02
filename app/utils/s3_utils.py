"""S3 helpers for the AWS Textract document extractor (owned utility).

Provides a boto3 ``create_s3_client`` factory and an ``S3Manager`` that the
Textract extractor uses to stage document bytes in S3 so Textract's
*asynchronous* ``StartDocumentAnalysis`` can process multi-page PDFs.

The manager deliberately keeps the boto3 calls thin and holds no network
state at construction time (clients connect lazily), so it is safe to
construct and useful with injected mocks in tests.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

_BOTO_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "standard"},
    connect_timeout=10,
    read_timeout=120,
)


def create_s3_client(*, region: str | None = None, **kwargs: Any) -> Any:
    """Create an S3 boto3 client. Callers may inject a mock instead."""
    return boto3.client(
        "s3",
        region_name=region
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1",
        config=_BOTO_CONFIG,
        **kwargs,
    )


class S3Manager:
    """Stages documents in S3 for AWS Textract async processing."""

    def __init__(
        self,
        *,
        region: str | None = None,
        bucket_name: str = "",
        prefix: str = "document-uploads",
        temp_expiry_days: int = 1,
        s3_client: Any | None = None,
    ) -> None:
        self.s3_client: Any = s3_client or create_s3_client(region=region)
        self.bucket_name: str = bucket_name
        self.prefix: str = (prefix or "document-uploads").strip("/")
        self.temp_expiry_days: int = temp_expiry_days
        if not self.bucket_name:
            logger.warning("S3Manager initialized with an empty bucket_name")

    def _build_key(self, document_id: str, file_name: str) -> str:
        """Build a namespaced S3 object key for a document upload."""
        safe_name = os.path.basename(file_name or "upload.bin")
        if self.prefix:
            return f"{self.prefix}/{document_id}/{safe_name}"
        return f"{document_id}/{safe_name}"

    async def upload_file(
        self,
        *,
        file_path: str,
        document_id: str,
        file_name: str,
    ) -> str:
        """Upload a local file to S3 and return its object key."""
        key = self._build_key(document_id, file_name)
        await asyncio.to_thread(
            self.s3_client.upload_file, file_path, self.bucket_name, key
        )
        logger.info(
            "Uploaded %s to s3://%s/%s", file_path, self.bucket_name, key
        )
        return key

    async def delete_file(self, s3_key: str) -> None:
        """Delete a previously uploaded object from S3."""
        await asyncio.to_thread(
            self.s3_client.delete_object, Bucket=self.bucket_name, Key=s3_key
        )
        logger.info("Deleted s3://%s/%s", self.bucket_name, s3_key)

    def generate_presigned_url(
        self, s3_key: str, expires_in: int = 3600
    ) -> str:
        """Return a presigned GET URL for a staged object."""
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": s3_key},
            ExpiresIn=expires_in,
        )