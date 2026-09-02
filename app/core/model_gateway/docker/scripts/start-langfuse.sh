#!/usr/bin/env bash
# Start Langfuse locally via official Docker Compose (clone upstream if needed).
# Usage (from repo root): ./model_gateway/docker/scripts/start-langfuse.sh
# UI: http://localhost:3000

set -euo pipefail
DOCKER_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM_DIR="${DOCKER_ROOT}/langfuse-upstream"

if [[ ! -d "${UPSTREAM_DIR}/.git" ]]; then
  echo "Cloning Langfuse (official docker-compose) into model_gateway/docker/langfuse-upstream ..."
  git clone --depth 1 https://github.com/langfuse/langfuse.git "${UPSTREAM_DIR}"
fi

cd "${UPSTREAM_DIR}"
if [[ ! -f docker-compose.yml ]]; then
  echo "docker-compose.yml not found in ${UPSTREAM_DIR}" >&2
  exit 1
fi

echo ""
echo "IMPORTANT: Edit model_gateway/docker/langfuse-upstream/docker-compose.yml and replace # CHANGEME secrets before production use."
echo "Starting Langfuse (first start may take 2-3 minutes) ..."
echo ""
docker compose up -d

echo ""
echo "Langfuse UI: http://localhost:3000"
echo "Next: create a project, then Settings -> API keys -> set LANGFUSE_* in your app .env"
echo "  LANGFUSE_HOST=http://localhost:3000"
echo ""
echo "Logs: docker compose -f model_gateway/docker/langfuse-upstream/docker-compose.yml logs -f langfuse-web"
echo "Stop:  docker compose -f model_gateway/docker/langfuse-upstream/docker-compose.yml down"
