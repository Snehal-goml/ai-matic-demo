# Langfuse local stack (Docker)

Run Langfuse on your machine for development — no Langfuse Cloud account required (you still create **project API keys** inside the local UI).

## Quick start

From the repo root:

**Windows (PowerShell):**

```powershell
.\model_gateway\docker\scripts\start-langfuse.ps1
```

**Linux / macOS:**

```bash
chmod +x model_gateway/docker/scripts/start-langfuse.sh
./model_gateway/docker/scripts/start-langfuse.sh
```

| What | URL |
|------|-----|
| Langfuse UI | http://localhost:3000 |

Wait until logs show `Ready` (about 2–3 minutes on first start).

## Connect model_gateway

1. Open http://localhost:3000 → sign up / log in → create a **project**.
2. **Settings → API keys** → create keys.
3. In your app `.env`:

```env
TRACING_PROVIDER=langfuse
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

4. Run a completion and call `get_manager().shutdown()` in scripts (see [LANGFUSE.md](../../observability/LANGFUSE.md)).

## Manual setup (without helper script)

```bash
git clone https://github.com/langfuse/langfuse.git model_gateway/docker/langfuse-upstream
cd model_gateway/docker/langfuse-upstream
# Edit docker-compose.yml — update lines marked # CHANGEME
docker compose up -d
```

Official docs: https://langfuse.com/self-hosting/deployment/docker-compose

## Stop

```bash
cd model_gateway/docker/langfuse-upstream
docker compose down
```

Add `-v` to remove volumes (deletes local trace data).

## Notes

- The clone lives in `model_gateway/docker/langfuse-upstream/` (gitignored). It uses Langfuse’s official compose (Postgres, ClickHouse, Redis, MinIO).
- For production self-hosting, follow [Langfuse deployment docs](https://langfuse.com/docs/deployment/self-host) (Kubernetes / HA), not this dev compose alone.
