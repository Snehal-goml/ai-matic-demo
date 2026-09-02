"""
Multimodal (image) embedding helper for RAG.

Gateway currently provides text embedding parity only. Image / combined
text+image embeddings stay behind this small RAG util and use Bedrock Runtime
directly — do not fork model_gateway for this gap.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Awaitable, Callable, Optional

import boto3

logger = logging.getLogger(__name__)

TextEmbedFn = Callable[[str], Awaitable[list]]


class MultimodalEmbedder:
    """Isolated multimodal embedding path (image / text+image)."""

    def __init__(
        self,
        *,
        multimodal_model_id: Optional[str],
        region: str,
        text_embed: TextEmbedFn,
        max_pixels: int = 20_000_000,
    ) -> None:
        self.multimodal_embedding_model_id = multimodal_model_id
        self._text_embed = text_embed
        self.max_pixels = max_pixels
        self.max_image_size = (4096, 4096)
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def _resize_image_for_bedrock(self, image_base64: str) -> str:
        from PIL import Image

        raw = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(raw))
        img.thumbnail(self.max_image_size)
        buf = io.BytesIO()
        fmt = (img.format or "PNG").upper()
        if fmt not in ("PNG", "JPEG", "JPG", "WEBP"):
            fmt = "PNG"
        img.save(buf, format="JPEG" if fmt in ("JPEG", "JPG") else fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _invoke_image_model(self, body: dict) -> list:
        model_id = self.multimodal_embedding_model_id
        if not model_id:
            raise ValueError(
                "Multimodal embedding model not configured. "
                "Set BEDROCK_MULTIMODAL_EMBEDDING_MODEL_ID / MULTIMODAL_EMBEDDING_MODEL_ID."
            )
        try:
            response = self._client.invoke_model(
                body=json.dumps(body),
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response.get("body").read())
            embedding = response_body.get("embedding")
            if not embedding:
                raise ValueError("No embedding returned from multimodal model")
            return embedding
        except Exception as e:
            error_str = str(e).lower()
            if "exceeds max pixels" in error_str or "image exceeds" in error_str:
                if "inputImage" not in body:
                    raise
                logger.warning("Image exceeds Bedrock limits; resizing and retrying")
                body = dict(body)
                body["inputImage"] = self._resize_image_for_bedrock(body["inputImage"])
                response = self._client.invoke_model(
                    body=json.dumps(body),
                    modelId=model_id,
                    contentType="application/json",
                    accept="application/json",
                )
                response_body = json.loads(response.get("body").read())
                embedding = response_body.get("embedding")
                if not embedding:
                    raise ValueError("No embedding returned from multimodal model")
                return embedding
            raise

    async def embed_multimodal(
        self,
        text: Optional[str] = None,
        image_base64: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> list:
        if image_base64 and not image_base64.strip():
            image_base64 = None
        if image_bytes is not None and len(image_bytes) == 0:
            image_bytes = None

        # Text-only → gateway text embedder
        if text and not image_base64 and not image_bytes:
            return await self._text_embed(text)

        if image_bytes and not image_base64:
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        if (image_base64 or image_bytes) and not text:
            return self._invoke_image_model({"inputImage": image_base64})

        if text and image_base64:
            return self._invoke_image_model(
                {"inputText": text, "inputImage": image_base64}
            )

        raise ValueError("Must provide at least text or image for embedding")
