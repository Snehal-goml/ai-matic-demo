"""Textract boto3 client factory (owned by the Textract adapter)."""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.config import Config

_BOTO_CONFIG = Config(
    read_timeout=120,
    connect_timeout=10,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


def create_textract_client(*, region: str | None = None) -> Any:
    """Create a Textract client. Callers may inject a mock instead."""
    return boto3.client(
        "textract",
        region_name=region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        config=_BOTO_CONFIG,
    )
