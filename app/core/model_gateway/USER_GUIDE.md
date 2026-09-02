# Model Gateway — User guide

This guide walks through **AI Matic Model Gateway** (`model_gateway`) feature by feature. The gateway is a small, OpenAI-shaped layer for chat completions, optional embeddings, token counting, and pluggable providers—including optional **multi-model routing** driven by environment configuration.

---

## Table of contents

1. [What you install and import](#1-what-you-install-and-import)
2. [Chat completions (sync)](#2-chat-completions-sync)
3. [Chat completions (async)](#3-chat-completions-async)
4. [How the gateway picks a provider](#4-how-the-gateway-picks-a-provider)
5. [OpenAI](#5-openai)
6. [Azure OpenAI](#6-azure-openai)
7. [AWS Bedrock](#7-aws-bedrock)
8. [Streaming responses](#8-streaming-responses)
9. [Request parameters (temperature, max_tokens, etc.)](#9-request-parameters-temperature-max_tokens-etc)
10. [Legacy text completion API](#10-legacy-text-completion-api)
11. [Embeddings](#11-embeddings)
12. [Token counting](#12-token-counting)
13. [Custom providers](#13-custom-providers)
14. [Model routing (aliases, groups, retry, circuit breaker)](#14-model-routing-aliases-groups-retry-circuit-breaker)
15. [Exceptions and troubleshooting](#15-exceptions-and-troubleshooting)
16. [Smoke tests](#16-smoke-tests)

---

## 1. What you install and import

Install project dependencies from the repository root (see root `requirements.txt`).

**Chat and legacy text APIs** live in `model_gateway.aim_main`:

```python
from model_gateway.aim_main import completion, acompletion, text_completion, atext_completion
```

**Package-level helpers** are imported from `model_gateway`:

```python
import model_gateway

model_gateway.token_counter(...)
model_gateway.embedding(...)
model_gateway.register_custom_provider(provider="...", custom_handler=...)
```

---

## 2. Chat completions (sync)

Use `completion()` for OpenAI-style chat: a **model** string and a **messages** list.

```python
from model_gateway.aim_main import completion

resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    custom_llm_provider="openai",
    max_tokens=60,
)

print(resp.choices[0].message.content)
```

When the underlying provider is **OpenAI or Azure**, the return value is the **OpenAI SDK** response object (same attributes as `openai.OpenAI().chat.completions.create(...)`).

When the provider is **Bedrock**, the gateway returns a **plain dict** shaped like a chat completion (see [AWS Bedrock](#7-aws-bedrock)).

---

## 3. Chat completions (async)

Use `acompletion()` with the same arguments as `completion()`, but `await` the result.

```python
from model_gateway.aim_main import acompletion

resp = await acompletion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Say hello."}],
    custom_llm_provider="openai",
    max_tokens=60,
)
```

Async Bedrock calls run the synchronous Bedrock path in a thread pool (`asyncio.to_thread`).

---

## 4. How the gateway picks a provider

Resolution order (simplified):

1. **`custom_llm_provider`** — If you pass this, it wins. A `model` value like `myprovider/foo` can also be split when `custom_llm_provider` matches the prefix.
2. **`provider/model` strings** — For example `openai/gpt-4.1-mini`, `azure/my-deployment`, `bedrock/anthropic.claude-...`. Built-in recognized prefixes include `openai`, `azure`, and `bedrock`.
3. **Bedrock ARNs** — If `model` looks like an AWS Bedrock ARN (`arn:...:bedrock:...`), the provider is treated as **bedrock**.
4. **Environment heuristics** — If `AZURE_OPENAI_API_KEY` or `AZURE_API_BASE` is set, the default provider becomes **azure**; otherwise **openai**.

If [model routing](#14-model-routing-aliases-groups-retry-circuit-breaker) is configured via env, a routed **alias** or **group name** can replace a single static model with a list of candidates (unless you set `custom_llm_provider`, which **disables** routing for that call).

---

## 5. OpenAI

- Pass **`custom_llm_provider="openai"`** or rely on default resolution when Azure env vars are not set.
- Set **`OPENAI_API_KEY`** (and optionally **`OPENAI_API_BASE`**) in the environment, or pass **`api_key`** / **`api_base`** into each call.

```python
resp = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hi!"}],
    custom_llm_provider="openai",
    api_key="sk-...",  # optional if env is set
    max_tokens=50,
)
```

---

## 6. Azure OpenAI

- Use **`custom_llm_provider="azure"`**.
- Pass **`api_base`** as your Azure OpenAI endpoint (resource URL).
- Pass **`api_version`** as a top-level argument; it is forwarded into the Azure client (not left inside the generic optional-params dict for the OpenAI client).

Typical env vars: **`AZURE_OPENAI_API_KEY`**, **`AZURE_API_BASE`**, **`AZURE_API_VERSION`**.

```python
resp = completion(
    model="YOUR_DEPLOYMENT_NAME",
    messages=[{"role": "user", "content": "Hi!"}],
    custom_llm_provider="azure",
    api_base="https://YOUR_RESOURCE.openai.azure.com",
    api_version="2024-02-15-preview",
    max_tokens=50,
)
```

---

## 7. AWS Bedrock

- Prefer **`bedrock/<model_id>`** as `model`, or pass a full **Bedrock inference ARN** as `model` (no prefix required).
- Uses **`boto3`** Bedrock Runtime in region **`AWS_REGION`** or **`AWS_DEFAULT_REGION`** (default `us-east-1`).
- Chat uses the **Converse** API; only **user** and **assistant** message roles are forwarded.
- Response is a **dict** with `choices`, `model`, and `object: "chat.completion"` (not the OpenAI SDK object).

```python
resp = completion(
    model="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
    messages=[{"role": "user", "content": "Write a haiku about rain."}],
    max_tokens=120,
)
text = resp["choices"][0]["message"]["content"]
```

Optional **`outputConfig`** can be passed through Bedrock via `kwargs` into `optional_params` if your call stack supplies it (see `providers/bedrock.py`).

**Note:** The Bedrock embedding helper strips a `bedrock/` prefix from the model id before calling `invoke_model`.

---

## 8. Streaming responses

Pass **`stream=True`** to `completion` / `acompletion` (or the text-completion wrappers). For **OpenAI and Azure**, the gateway returns the **same stream iterator** as the OpenAI SDK.

```python
stream = completion(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
    custom_llm_provider="openai",
    stream=True,
    max_tokens=100,
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if delta and getattr(delta, "content", None):
        print(delta.content, end="")
```

**Routing behavior:** When model routing is enabled, **streaming disables per-candidate retry** (only one attempt per candidate; no backoff retry loop). This avoids ambiguous behavior after bytes have already been delivered.

---

## 9. Request parameters (temperature, max_tokens, etc.)

Supported first-class arguments on `completion` / `acompletion` include:

| Parameter | Role |
|-----------|------|
| `temperature`, `top_p` | Sampling |
| `n` | Number of completions |
| `stream` | Streaming |
| `stop` | Stop sequences (string or list) |
| `max_tokens` | Upper bound on generated tokens |
| `presence_penalty`, `frequency_penalty` | OpenAI-style penalties |
| `logit_bias` | Token logit bias map |
| `user` | End-user id (also used for routing / team selection; see routing section) |
| `custom_llm_provider` | Force provider |
| `api_key`, `api_base`, `timeout` | Client overrides |

Additional **`kwargs`** with non-`None` values are merged into the request (e.g. **`response_format`** for JSON mode on OpenAI).

---

## 10. Legacy text completion API

**`text_completion`** / **`atext_completion`** accept a string or list of strings as **`prompt`**, wrap them as user messages, and delegate to **`completion`** / **`acompletion`**.

```python
from model_gateway.aim_main import text_completion

resp = text_completion(
    prompt="Summarize: ...",
    model="gpt-4.1-mini",
    custom_llm_provider="openai",
    max_tokens=200,
)
# OpenAI SDK shape: resp.choices[0].text
```

---

## 11. Embeddings

Call **`model_gateway.embedding`** with a **`model`**, **`input`** (string or list of strings), and optional provider overrides.

Supported paths:

- **OpenAI** (default or `custom_llm_provider="openai"`) — OpenAI SDK `embeddings.create`.
- **Bedrock** — Titan-style models via `invoke_model`; returns an OpenAI-like **`{"data": [{"embedding": [...]}, ...]}`** dict.
- **Custom providers** — If the registered handler defines **`embedding`**, it will be used.

```python
import model_gateway

r = model_gateway.embedding(
    model="text-embedding-3-small",
    input=["hello", "world"],
    custom_llm_provider="openai",
)
```

---

## 12. Token counting

**`model_gateway.token_counter`** estimates tokens using **`tiktoken`**. Pass either **`messages`** or **`text`** (not both required by the API; if both are omitted, it returns `0`).

```python
import model_gateway

n = model_gateway.token_counter(model="gpt-4", messages=[{"role": "user", "content": "Hello"}])
n2 = model_gateway.token_counter(model="gpt-4", text="Hello")
```

If `tiktoken` does not recognize the model name, encoding falls back to **`cl100k_base`**.

---

## 13. Custom providers

Register a handler with **`model_gateway.register_custom_provider`**. The handler **must** implement **`completion(...)`**. Optionally implement **`acompletion`**, **`embedding`**, and **`aembedding`** for async and embeddings.

Expected **`completion`** signature (conceptually):

`completion(model, messages, optional_params, api_key=None, api_base=None, timeout=None)`

You may return either an OpenAI-like dict (as in the routing tests) or your own object—callers should match the provider they register.

```python
import model_gateway

class MyBackend:
    def completion(self, *, model, messages, optional_params, api_key=None, api_base=None, timeout=None):
        return {
            "choices": [{"message": {"role": "assistant", "content": "pong"}, "finish_reason": "stop", "index": 0}],
            "model": model,
            "object": "chat.completion",
        }

model_gateway.register_custom_provider(provider="mybackend", custom_handler=MyBackend())
```

---

## 14. Model routing (aliases, groups, retry, circuit breaker)

When **`AIM_ROUTER_CONFIG_JSON`** (raw JSON string) or **`AIM_ROUTER_CONFIG_PATH`** (file path) is set, the gateway loads a **router config**. If the **`model`** you pass matches an **alias**, a **group name**, or a **per-team alias override**, the call is expanded into an **ordered list of provider+model candidates** instead of a single backend.

### 14.1 Bypass routing

If you pass **`custom_llm_provider`**, routing is **not** applied for that request (you already fixed the provider).

### 14.2 Aliases and groups

- **`aliases`**: map a short name (e.g. `"general"`) to `{"group": "general_group"}`.
- **`groups`**: named groups contain **`strategy`** (currently **`weighted_hash`**) and a non-empty **`candidates`** list.
- **Direct group address**: if **`model`** equals a group name, that group is used without an alias.

### 14.3 Weighted selection and failover order

For **`weighted_hash`**, the gateway picks a **primary** candidate using a stable hash of **`f"{user or 'anonymous'}::{group.name}"`** and candidate **weights**. Remaining candidates are tried **in rotated order** as fallbacks if earlier attempts fail.

### 14.4 Per-team alias overrides

Under **`overrides.teams`**, each team may define **`alias_overrides`**: maps a logical model name to `{"group": "..."}`.

The **`user`** string selects the team:

- If **`user`** contains **`:`**, the part **before** the first colon is the **team id** (e.g. `"teamA:alice"` → team **`teamA`**).
- If there is **no** colon, the entire **`user`** string is the team id.

### 14.5 Candidate fields

Each candidate may include:

| Field | Meaning |
|-------|---------|
| `provider` | Provider id (`openai`, `azure`, `bedrock`, or a registered custom provider) |
| `model` | Model id or deployment name for that provider |
| `weight` | Relative weight for `weighted_hash` (default 100) |
| `api_base` | Optional base URL / endpoint for this candidate |
| `api_key_env` | Name of an environment variable holding the API key for this candidate |
| `timeout_s` | Optional per-attempt timeout override |

### 14.6 Retry policy

Top-level **`retry`** in JSON:

| Field | Default | Meaning |
|-------|---------|---------|
| `max_attempts` | 1 | Retries **within** the same candidate for certain errors |
| `base_delay_ms` | 200 | Exponential backoff base |
| `max_delay_ms` | 2000 | Backoff cap |
| `jitter` | `"full"` | `"none"` or `"full"` randomization |
| `retry_on` | `timeout`, `rate_limit`, `http_5xx` | Which error categories retry |

Errors are classified using **OpenAI SDK** exception types where possible (`APITimeoutError`, `RateLimitError`, HTTP 5xx / 429, plus a simple `"timed out"` string heuristic).

### 14.7 Circuit breaker

Top-level **`circuit_breaker`**:

- After **`open_after_failures`** failures for the same **(provider, model, api_base)** key, that candidate is **skipped** until **`cooldown_seconds`** elapses.

### 14.8 Example config

```json
{
  "version": 1,
  "aliases": {
    "general": { "group": "general_group" }
  },
  "groups": {
    "general_group": {
      "strategy": "weighted_hash",
      "candidates": [
        { "provider": "openai", "model": "gpt-4.1-mini", "weight": 90 },
        { "provider": "openai", "model": "gpt-4.1-nano", "weight": 10 }
      ]
    }
  },
  "retry": {
    "max_attempts": 2,
    "base_delay_ms": 200,
    "max_delay_ms": 2000,
    "jitter": "full",
    "retry_on": ["timeout", "rate_limit", "http_5xx"]
  },
  "circuit_breaker": {
    "open_after_failures": 5,
    "cooldown_seconds": 30
  },
  "overrides": {
    "teams": {
      "teamA": {
        "alias_overrides": {
          "general": { "group": "other_group" }
        }
      }
    }
  }
}
```

Set either:

- `AIM_ROUTER_CONFIG_JSON='{"version":1, ... }'`, or  
- `AIM_ROUTER_CONFIG_PATH=/path/to/config.json`

---

## 15. Exceptions and troubleshooting

- **`model_gateway.exceptions.ModelGatewayError`** — Base type with optional **`model`**, **`custom_llm_provider`**, and **`original_exception`** (not all call sites may wrap errors in this type; low-level SDK errors often propagate directly).
- **`ValueError`** — Unknown provider, missing handler, invalid router JSON, etc.
- **Routing:** If every candidate is circuit-open or fails, the **last exception** is re-raised, or you may see **`RuntimeError("Routing configured but no candidates were available")`** when nothing could be attempted.

**Bedrock:** Confirm AWS credentials and region; chat only forwards **user** / **assistant** roles.

**Azure:** Ensure **`api_version`** is compatible with your resource and that **`model`** is the **deployment** name.

---

## 16. Smoke tests

From the repository root:

```bash
python test_aim_model_gateway.py --providers openai
python test_aim_model_gateway.py --providers bedrock
python test_aim_model_gateway.py --providers routing
```

- **openai** — Requires **`OPENAI_API_KEY`**.
- **bedrock** — Requires working **AWS** credentials and a valid Bedrock model id or ARN.
- **routing** — Uses a **mock** custom provider and temporary **`AIM_ROUTER_CONFIG_JSON`** (no real API keys).

---

## Quick reference — environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY`, `OPENAI_API_BASE` | OpenAI auth and optional base URL |
| `AZURE_OPENAI_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` | Azure defaults |
| `AWS_REGION`, `AWS_DEFAULT_REGION` | Bedrock region |
| Standard `AWS_*` credential vars / profile | Bedrock auth via boto3 |
| `AIM_ROUTER_CONFIG_JSON` or `AIM_ROUTER_CONFIG_PATH` | Enable model routing |

---

For a shorter overview, see the repository [README.md](../README.md).
