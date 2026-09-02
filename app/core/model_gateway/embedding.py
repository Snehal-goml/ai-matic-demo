from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import openai

import app.core.model_gateway as model_gateway
from app.core.model_gateway.core import get_llm_provider


def embedding(
    *,
    model: str,
    input: Union[str, List[str]],
    custom_llm_provider: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Minimal embeddings endpoint for `model_gateway`.

    Supported:
    - OpenAI-compatible embeddings via OpenAI SDK
    - AWS Bedrock embeddings via Bedrock Runtime (Titan text embeddings)
    """

    resolved_model, provider, dyn_key, dyn_base = get_llm_provider(
        model=model,
        custom_llm_provider=custom_llm_provider,
        api_key=api_key,
        api_base=api_base,
    )
    if dyn_key is not None:
        api_key = dyn_key
    if dyn_base is not None:
        api_base = dyn_base

    if provider in (None, "openai") or provider in model_gateway.openai_compatible_providers:
        base_url = api_base or model_gateway.api_base or "https://api.openai.com/v1"
        key = api_key or model_gateway.api_key or model_gateway.openai_key
        client = openai.OpenAI(api_key=key, base_url=base_url)
        resp = client.embeddings.create(model=resolved_model, input=input)  # type: ignore[arg-type]
        return resp.model_dump()

    if provider == "bedrock":
        from app.core.model_gateway.providers import bedrock as bedrock_provider

        vectors = bedrock_provider.embedding(model=resolved_model, input=input)
        data = [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)]
        return {"object": "list", "data": data, "model": model}

    raise ValueError(f"Unsupported embeddings provider: {provider!r}")

