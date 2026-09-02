"""Shared process liveness and registered feature readiness probes."""

import inspect
import logging
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, status

from app.core.feature_contract import HealthCheck

logger = logging.getLogger(__name__)
router = APIRouter()
_health_checks: dict[str, HealthCheck] = {}


def register_health_checks(slug: str, checks: Mapping[str, HealthCheck]) -> None:
    """Register readiness checks using feature-qualified names."""
    for name, check in checks.items():
        _health_checks[f"{slug}.{name}"] = check


async def _run_check(check: HealthCheck) -> Any:
    result = check()
    return await result if inspect.isawaitable(result) else result


@router.get("")
@router.get("/", include_in_schema=False)
async def health() -> dict[str, str]:
    """Liveness alias used by load balancers and local checks."""
    return {"status": "ok"}


@router.get("/live")
async def live() -> dict[str, str]:
    """Returns 200 if the process is up. No dependency checks."""
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """Run readiness checks registered by enabled features."""
    results: dict[str, Any] = {}
    failures: list[str] = []
    for name, check in _health_checks.items():
        try:
            result = await _run_check(check)
            results[name] = result
            if result is False or (
                isinstance(result, dict) and result.get("success") is False
            ):
                failures.append(name)
        except Exception as exc:
            logger.warning("Readiness check %s failed: %s", name, exc)
            results[name] = {"success": False, "error": str(exc)}
            failures.append(name)
    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "failed": failures, "checks": results},
        )
    return {"status": "ready", "checks": results}
