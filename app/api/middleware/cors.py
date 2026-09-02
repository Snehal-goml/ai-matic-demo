"""Shared CORS middleware configuration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def add_cors_middleware(app: FastAPI) -> None:
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_split(settings.CORS_ALLOW_ORIGINS),
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=_split(settings.CORS_ALLOW_METHODS),
        allow_headers=_split(settings.CORS_ALLOW_HEADERS),
        expose_headers=["*"],
    )
