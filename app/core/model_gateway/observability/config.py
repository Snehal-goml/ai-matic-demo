from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Literal, Optional


TracingProviderName = Literal["otel", "langfuse", "goml_tracer", "noop"]


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class ObservabilityConfig:
    enabled: bool = False
    tracing_enabled: bool = False
    tracing_provider: TracingProviderName = "noop"

    request_logging_enabled: bool = True
    response_logging_enabled: bool = True
    log_bodies: bool = False
    tracing_capture_io: bool = True
    log_level: str = "info"

    pii_redaction_enabled: bool = True
    pii_redaction_fields: List[str] = field(
        default_factory=lambda: [
            "email",
            "phone",
            "token",
            "authorization",
            "api_key",
            "password",
            "ssn",
        ]
    )

    metrics_enabled: bool = True
    prometheus_enabled: bool = False

    otel_endpoint: Optional[str] = None
    otel_service_name: str = "goml-gateway"
    otel_exporter: str = "otlp_grpc"

    langfuse_host: Optional[str] = None
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_project_name: Optional[str] = None
    langfuse_organization_name: Optional[str] = None
    langfuse_environment: Optional[str] = None

    goml_tracer_db_path: str = "./data/goml_tracer.db"
    goml_tracer_retention_days: int = 30
    goml_tracer_sampling_rate: float = 1.0

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        enabled = _env_bool("OBSERVABILITY_ENABLED", False)
        tracing_enabled = _env_bool("TRACING_ENABLED", enabled)
        provider = os.getenv("TRACING_PROVIDER", "noop").strip().lower()
        if provider not in ("otel", "langfuse", "goml_tracer", "noop"):
            provider = "noop"
        if not tracing_enabled:
            provider = "noop"

        pii_fields_raw = os.getenv(
            "PII_REDACTION_FIELDS",
            "email,phone,token,authorization,api_key,password,ssn",
        )
        pii_fields = [f.strip() for f in pii_fields_raw.split(",") if f.strip()]

        tracing_capture_io_default = tracing_enabled and provider == "otel"
        tracing_capture_io = _env_bool(
            "TRACING_CAPTURE_IO",
            _env_bool("LOG_BODIES", tracing_capture_io_default),
        )

        return cls(
            enabled=enabled,
            tracing_enabled=tracing_enabled,
            tracing_provider=provider,  # type: ignore[arg-type]
            request_logging_enabled=_env_bool("REQUEST_LOGGING_ENABLED", True),
            response_logging_enabled=_env_bool("RESPONSE_LOGGING_ENABLED", True),
            log_bodies=_env_bool("LOG_BODIES", False),
            tracing_capture_io=tracing_capture_io,
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
            pii_redaction_enabled=_env_bool("PII_REDACTION_ENABLED", True),
            pii_redaction_fields=pii_fields,
            metrics_enabled=_env_bool("METRICS_ENABLED", True),
            prometheus_enabled=_env_bool("PROMETHEUS_ENABLED", False),
            otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            otel_service_name=os.getenv("OTEL_SERVICE_NAME", "goml-gateway"),
            otel_exporter=os.getenv("OTEL_EXPORTER", "otlp_grpc"),
            langfuse_host=os.getenv("LANGFUSE_HOST"),
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            langfuse_project_name=os.getenv("LANGFUSE_PROJECT_NAME"),
            langfuse_organization_name=os.getenv("LANGFUSE_ORGANIZATION_NAME"),
            langfuse_environment=os.getenv("LANGFUSE_ENVIRONMENT")
            or os.getenv("LANGFUSE_TRACING_ENVIRONMENT"),
            goml_tracer_db_path=os.getenv("GOML_TRACER_DB_PATH", "./data/goml_tracer.db"),
            goml_tracer_retention_days=_env_int("GOML_TRACER_RETENTION_DAYS", 30),
            goml_tracer_sampling_rate=_env_float("GOML_TRACER_SAMPLING_RATE", 1.0),
        )
