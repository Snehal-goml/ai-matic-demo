"""
Document Loaders

This module provides document loaders for various file formats.
"""

from app.core.pipelines.rag.ingestion.loaders.base import DocumentLoader, Document
from app.core.pipelines.rag.ingestion.loaders.text import TextLoader
from app.core.pipelines.rag.ingestion.loaders.pdf import PDFLoader
from app.core.pipelines.rag.ingestion.loaders.json_loader import JSONLoader
from app.core.pipelines.rag.ingestion.loaders.textract import TextractLoader
from app.core.pipelines.rag.ingestion.loaders.image import ImageLoader

__all__ = [
    "DocumentLoader",
    "Document",
    "TextLoader",
    "PDFLoader",
    "JSONLoader",
    "TextractLoader",
    "ImageLoader",
]

