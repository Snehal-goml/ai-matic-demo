# Start Langfuse locally via official Docker Compose (clone upstream if needed).
# Usage (from repo root): .\model_gateway\docker\scripts\start-langfuse.ps1
# UI: http://localhost:3000

$ErrorActionPreference = "Stop"
$DockerRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$UpstreamDir = Join-Path $DockerRoot "langfuse-upstream"

if (-not (Test-Path (Join-Path $UpstreamDir ".git"))) {
    Write-Host "Cloning Langfuse (official docker-compose) into model_gateway/docker/langfuse-upstream ..."
    git clone --depth 1 https://github.com/langfuse/langfuse.git $UpstreamDir
}

Push-Location $UpstreamDir
try {
    if (-not (Test-Path "docker-compose.yml")) {
        throw "docker-compose.yml not found in $UpstreamDir"
    }
    Write-Host ""
    Write-Host "IMPORTANT: Edit model_gateway/docker/langfuse-upstream/docker-compose.yml and replace # CHANGEME secrets before production use."
    Write-Host "Starting Langfuse (first start may take 2-3 minutes) ..."
    Write-Host ""
    docker compose up -d
    Write-Host ""
    Write-Host "Langfuse UI: http://localhost:3000"
    Write-Host "Next: create a project, then Settings -> API keys -> set LANGFUSE_* in your app .env"
    Write-Host "  LANGFUSE_HOST=http://localhost:3000"
    Write-Host ""
    Write-Host "Logs: docker compose -f model_gateway/docker/langfuse-upstream/docker-compose.yml logs -f langfuse-web"
    Write-Host "Stop:  docker compose -f model_gateway/docker/langfuse-upstream/docker-compose.yml down"
}
finally {
    Pop-Location
}
