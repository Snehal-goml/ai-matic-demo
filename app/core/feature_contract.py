"""Contract implemented by independently composable application features."""

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from fastapi import APIRouter, FastAPI

LifecycleHook = Callable[[], Any]
HealthCheck = Callable[[], Any]
ConfigureApp = Callable[[FastAPI], None]


@dataclass(frozen=True)
class FeatureModule:
    slug: str
    router: APIRouter
    prefix: str
    tags: Sequence[str] = field(default_factory=tuple)
    health_checks: Mapping[str, HealthCheck] = field(default_factory=dict)
    on_startup: Optional[LifecycleHook] = None
    on_shutdown: Optional[LifecycleHook] = None
    configure_app: Optional[ConfigureApp] = None
