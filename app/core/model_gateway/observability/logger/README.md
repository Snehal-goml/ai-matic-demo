# Structured logging

JSON logs on stderr for request/response events when `REQUEST_LOGGING_ENABLED` / `RESPONSE_LOGGING_ENABLED` are true.

PII fields are redacted via `redact.py` before emit. Set `LOG_BODIES=false` in production.

Reference: `litellm/litellm_core_utils/redact_messages.py`, `Dump/docs/my-website/docs/observability/scrub_data.md`
