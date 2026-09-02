from __future__ import annotations

import re
from typing import Any, Iterable, List, MutableMapping, Union

_REDACTED = "[REDACTED]"

_DEFAULT_PII = frozenset(
    {
        "email",
        "phone",
        "token",
        "authorization",
        "api_key",
        "api-key",
        "x-api-key",
        "password",
        "ssn",
        "secret",
        "access_token",
        "refresh_token",
    }
)

_HEADER_RE = re.compile(r"^(authorization|x-api-key|api-key|cookie)$", re.I)


def redact_value(key: str, fields: Iterable[str]) -> bool:
    key_lower = key.lower().replace("-", "_")
    field_set = {f.lower().replace("-", "_") for f in fields}
    if key_lower in field_set or key_lower in _DEFAULT_PII:
        return True
    return bool(_HEADER_RE.match(key))


def redact_pii(
    data: Any,
    *,
    fields: Iterable[str],
    enabled: bool = True,
) -> Any:
    if not enabled:
        return data
    field_list = list(fields)
    return _redact_recursive(data, field_list)


def _redact_recursive(obj: Any, fields: List[str]) -> Any:
    if isinstance(obj, MutableMapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if redact_value(str(k), fields):
                out[k] = _REDACTED
            else:
                out[k] = _redact_recursive(v, fields)
        return out
    if isinstance(obj, list):
        return [_redact_recursive(i, fields) for i in obj]
    if isinstance(obj, tuple):
        return tuple(_redact_recursive(i, fields) for i in obj)
    return obj
