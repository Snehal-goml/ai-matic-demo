# Langfuse provider

Sends each completion as a Langfuse **trace** + **generation** (input, output, model, metadata).

**Full guide:** [`../../LANGFUSE.md`](../../LANGFUSE.md) — Cloud/self-hosted setup, UI, AWS (EC2/ECS/Lambda), troubleshooting.

## Quick env

```env
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

Requires: `pip install -r requirements.txt`

## Reference

- `litellm/integrations/langfuse/langfuse.py`
- `Dump/docs/my-website/docs/observability/langfuse_integration.md`
