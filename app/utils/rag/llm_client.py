"""
RAG LLM / embedding client backed by Foundation model_gateway.

Text completion and text embeddings go through the gateway.
Image / multimodal embeddings are isolated in multimodal_embed (gateway gap).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, List, Optional

from app.config.settings import settings
from app.core.model_gateway.aim_main import acompletion
from app.core.model_gateway import embedding as gateway_embedding
from app.utils.rag.multimodal_embed import MultimodalEmbedder

logger = logging.getLogger(__name__)


def _normalize_messages(messages: Any) -> list[dict[str, Any]]:
    """Convert LangChain-like or dict messages to OpenAI-style role/content dicts."""
    normalized: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or "user"
            content = msg.get("content", "")
            normalized.append({"role": role, "content": content})
            continue

        # LangChain BaseMessage duck-typing
        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
        content = getattr(msg, "content", str(msg))
        role_map = {
            "human": "user",
            "ai": "assistant",
            "system": "system",
            "user": "user",
            "assistant": "assistant",
        }
        role = role_map.get(str(msg_type).lower(), "user")
        normalized.append({"role": role, "content": content})
    return normalized


def _extract_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if content is not None:
            return content if isinstance(content, str) else str(content)
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            return message.get("content") or ""
    return str(response)


def _extract_embedding(response: Any) -> list[float]:
    if hasattr(response, "model_dump"):
        response = response.model_dump()
    data = (response or {}).get("data") if isinstance(response, dict) else None
    data = data or []
    if not data:
        raise ValueError("Model gateway returned no embedding")
    first = data[0]
    vector = (
        first.get("embedding")
        if isinstance(first, dict)
        else getattr(first, "embedding", None)
    )
    if not vector:
        raise ValueError("Model gateway returned no embedding")
    return vector


class GatewayLLMClient:
    """
    RAG LLM / embed client backed by Foundation model_gateway.

    Hot path: aim_main.acompletion + gateway embedding.
    Multimodal image embed: utils.rag.multimodal_embed (gateway text-only gap).
    """

    def __init__(self) -> None:
        self.llm_model_id = settings.MODEL_ID
        self.embedding_model_id = settings.EMBEDDING_MODEL_ID
        self.multimodal_embedding_model_id = getattr(
            settings, "BEDROCK_MULTIMODAL_EMBEDDING_MODEL_ID", None
        )
        self.provider = settings.LLM_PROVIDER
        self.timeout = getattr(settings, "LLM_TIMEOUT", 60)
        self._embedding_dim = self._get_embedding_dimension()
        self._multimodal = MultimodalEmbedder(
            multimodal_model_id=self.multimodal_embedding_model_id,
            region=settings.AWS_REGION,
            text_embed=self.embed,
        )
        # Compatibility: some call sites expect `.llm` — point at self
        self.llm = self
        logger.info(
            "GatewayLLMClient ready model=%s embed=%s dim=%s",
            self.llm_model_id,
            self.embedding_model_id,
            self._embedding_dim,
        )

    def _get_embedding_dimension(self) -> int:
        override = getattr(settings, "EMBEDDING_DIM", None)
        if override:
            return int(override)
        model_id = (self.embedding_model_id or "").lower()
        if "gemini-embedding" in model_id:
            return 3072
        if "text-embedding-3-small" in model_id:
            return 1536
        if "text-embedding-3-large" in model_id:
            return 3072
        if "titan-embed-text-v2" in model_id:
            return 1024
        if "titan-embed-text-v1" in model_id:
            return 1536
        if "titan-embed-image" in model_id or "titan-multimodal" in model_id:
            return 1024
        logger.warning(
            "Unknown embedding model %s; defaulting dimension to 1024", model_id
        )
        return 1024

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dim

    async def invoke(self, messages) -> str:
        """Invoke the LLM; returns response text content."""
        normalized = _normalize_messages(messages)
        logger.info("Invoking LLM via model_gateway (%s messages)", len(normalized))
        response = await acompletion(
            model=self.llm_model_id,
            messages=normalized,
            temperature=0.7,
            max_tokens=8192,
            custom_llm_provider=self.provider,
            timeout=self.timeout,
        )
        return _extract_content(response)

    async def ainvoke(self, messages) -> Any:
        """LangChain-style alias used if callers expect ChatModel.ainvoke."""
        content = await self.invoke(messages)

        class _Resp:
            def __init__(self, content: str):
                self.content = content

        return _Resp(content)

    async def invoke_structured_with_schema(self, messages, schema):
        """
        Best-effort structured output via gateway completion + JSON parse.

        Prefer schema validation when the model returns JSON; does not fork gateway.
        """
        normalized = _normalize_messages(messages)
        schema_name = getattr(schema, "__name__", str(schema))
        hint = (
            f"Respond with valid JSON matching the '{schema_name}' schema only."
        )
        if normalized and normalized[-1]["role"] == "user":
            content = normalized[-1]["content"]
            if isinstance(content, str):
                normalized[-1]["content"] = f"{content}\n\n{hint}"
        else:
            normalized.append({"role": "user", "content": hint})

        raw = await self.invoke(normalized)
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        data = json.loads(text)
        if hasattr(schema, "model_validate"):
            return schema.model_validate(data)
        return schema(**data)

    async def embed(self, text: str) -> list:
        """Generate a text embedding via model_gateway."""
        logger.info("Generating embedding via model_gateway (len=%s)", len(text))
        response = await asyncio.to_thread(
            gateway_embedding,
            model=self.embedding_model_id,
            input=text,
            custom_llm_provider=self.provider,
        )
        return _extract_embedding(response)

    async def embed_batch(self, texts: list) -> list:
        embeddings = []
        for text in texts:
            embeddings.append(await self.embed(text))
        return embeddings

    def embed_sync(self, text: str) -> list:
        response = gateway_embedding(
            model=self.embedding_model_id,
            input=text,
            custom_llm_provider=self.provider,
        )
        return _extract_embedding(response)

    async def embed_multimodal(
        self,
        text: Optional[str] = None,
        image_base64: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> list:
        """Prefer gateway text embed; image path uses multimodal helper."""
        return await self._multimodal.embed_multimodal(
            text=text,
            image_base64=image_base64,
            image_bytes=image_bytes,
        )
