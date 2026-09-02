"""Settings shared by the application foundation."""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppSettings(BaseSettings):
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"
    AWS_REGION: str = "us-east-1"
    APP_TITLE: str = "AI Matic Application"
    APP_DESCRIPTION: str = "AI Matic composed application"
    APP_VERSION: str = "2.0.0"
    SHUTDOWN_DRAIN_SECONDS: int = 30

    AUTH_METHOD: str = "none"
    API_KEY: str = ""
    API_KEYS: str = ""
    BEARER_TOKEN: str = ""
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"

    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60

    CORS_ALLOW_ORIGINS: str = "*"
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: str = "GET,OPTIONS,POST,PUT,DELETE"
    CORS_ALLOW_HEADERS: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env" if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else None,
        case_sensitive=True,
        extra="ignore",
    )
