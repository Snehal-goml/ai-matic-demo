"""Shared pytest fixtures"""

import pytest


@pytest.fixture
def app():
    """FastAPI app for TestClient (import after feature env is set in slug conftest)."""
    from app.main import app as fastapi_app

    return fastapi_app
