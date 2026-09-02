from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Union

import boto3


def _bedrock_client():
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
    return boto3.client("bedrock-runtime", region_name=region)


def bedrock_embedding(
    *,
    model: str,
    input: Union[str, List[str]],
    timeout: Optional[Any] = None,
    **kwargs: Any,
) -> Any:
    """
    Minimal embedding wrapper for Bedrock Titan embedding models.

    Returns an OpenAI-like dict: {"data": [{"embedding": [...]}, ...]}
    """

    _ = timeout  # boto3 doesn't expose a simple per-request timeout here
    client = _bedrock_client()
    model_id = model.replace("bedrock/", "")

    if isinstance(input, list):
        vectors: List[List[float]] = []
        for text in input:
            body = json.dumps({"inputText": text})
            resp = client.invoke_model(modelId=model_id, body=body)
            payload = json.loads(resp["body"].read().decode("utf-8"))
            vec = payload.get("embedding") or payload.get("vector") or []
            vectors.append([float(x) for x in vec])
        return {"data": [{"embedding": v} for v in vectors]}

    body = json.dumps({"inputText": input})
    resp = client.invoke_model(modelId=model_id, body=body)
    payload = json.loads(resp["body"].read().decode("utf-8"))
    vec = payload.get("embedding") or payload.get("vector") or []
    return {"data": [{"embedding": [float(x) for x in vec]}]}


def bedrock_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    optional_params: Dict[str, Any],
    timeout: Optional[Any] = None,
) -> Any:
    """
    Minimal Bedrock chat via Converse API (best-effort).

    Returns an OpenAI-like dict: {"choices":[{"message":{"role":"assistant","content":...}}], ...}
    """

    _ = timeout  # boto3 doesn't expose a simple per-request timeout here
    client = _bedrock_client()
    model_id = model.replace("bedrock/", "")

    converse_messages: List[Dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        if content is None:
            continue
        converse_messages.append({"role": role, "content": [{"text": str(content)}]})

    max_tokens = optional_params.get("max_tokens")
    temperature = optional_params.get("temperature")
    top_p = optional_params.get("top_p")

    resp = client.converse(
        modelId=model_id,
        messages=converse_messages,
        inferenceConfig={
            **({} if max_tokens is None else {"maxTokens": int(max_tokens)}),
            **({} if temperature is None else {"temperature": float(temperature)}),
            **({} if top_p is None else {"topP": float(top_p)}),
        },
        **(
            {}
            if "outputConfig" not in optional_params
            else {"outputConfig": optional_params["outputConfig"]}
        ),
    )

    out_text = ""
    try:
        out_blocks = resp.get("output", {}).get("message", {}).get("content", [])
        if isinstance(out_blocks, list):
            out_text = "".join(
                [b.get("text", "") for b in out_blocks if isinstance(b, dict)]
            )
    except Exception:
        out_text = ""

    usage_block: Dict[str, Any] = {}
    try:
        raw_usage = resp.get("usage") or resp.get("Usage") or {}
        if isinstance(raw_usage, dict):
            inp = (
                raw_usage.get("inputTokens")
                or raw_usage.get("input_tokens")
                or raw_usage.get("prompt_tokens")
            )
            out = (
                raw_usage.get("outputTokens")
                or raw_usage.get("output_tokens")
                or raw_usage.get("completion_tokens")
            )
            total = raw_usage.get("totalTokens") or raw_usage.get("total_tokens")
            if inp is not None:
                usage_block["prompt_tokens"] = int(inp)
            if out is not None:
                usage_block["completion_tokens"] = int(out)
            if total is not None:
                usage_block["total_tokens"] = int(total)
            elif inp is not None and out is not None:
                usage_block["total_tokens"] = int(inp) + int(out)
    except (TypeError, ValueError, AttributeError):
        usage_block = {}

    result: Dict[str, Any] = {
        "choices": [
            {
                "message": {"role": "assistant", "content": out_text},
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "model": model,
        "object": "chat.completion",
    }
    if usage_block:
        result["usage"] = usage_block
    return result


async def abedrock_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    optional_params: Dict[str, Any],
    timeout: Optional[Any] = None,
) -> Any:
    return await asyncio.to_thread(
        bedrock_chat_completion,
        model=model,
        messages=messages,
        optional_params=optional_params,
        timeout=timeout,
    )
