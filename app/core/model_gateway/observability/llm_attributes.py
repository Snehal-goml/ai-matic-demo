from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def infer_provider_from_model(model: Optional[str]) -> Optional[str]:
    if not model or not isinstance(model, str):
        return None
    if model.startswith("arn:") and ":bedrock:" in model:
        return "bedrock"
    if model.startswith("bedrock/"):
        return "bedrock"
    if "/" in model:
        prefix = model.split("/", 1)[0]
        if prefix in ("openai", "azure", "bedrock"):
            return prefix
    return None


def extract_usage_from_response(
    response: Any,
) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (input_tokens, output_tokens, total_tokens)."""
    usage: Any = None
    if isinstance(response, dict):
        usage = response.get("usage")
    else:
        usage = getattr(response, "usage", None)

    if usage is None:
        return None, None, None

    if isinstance(usage, dict):
        inp = usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("inputTokens")
        out = usage.get("completion_tokens") or usage.get("output_tokens") or usage.get(
            "outputTokens"
        )
        total = usage.get("total_tokens") or usage.get("totalTokens")
    else:
        inp = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        out = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
        total = getattr(usage, "total_tokens", None)

    def _to_int(v: Any) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    inp_i, out_i, total_i = _to_int(inp), _to_int(out), _to_int(total)
    if total_i is None and inp_i is not None and out_i is not None:
        total_i = inp_i + out_i
    return inp_i, out_i, total_i


def extract_assistant_text(response: Any) -> Optional[str]:
    if response is None:
        return None
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            return str(content) if content is not None else None
        return None
    choices = getattr(response, "choices", None)
    if choices:
        first = choices[0]
        message = getattr(first, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            return str(content) if content is not None else None
    return None


def summarize_messages_for_span(messages: List[Dict[str, Any]], *, max_len: int = 4000) -> str:
    try:
        text = json.dumps(messages, default=str)
    except (TypeError, ValueError):
        text = str(messages)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text
