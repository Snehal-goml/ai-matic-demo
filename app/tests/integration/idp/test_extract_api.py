"""Integration test for the namespaced IDP extraction endpoint."""

import pytest
from fastapi.testclient import TestClient

try:
    from app.adapters.file_extraction.extractors.custom_extractor.extractor import (  # noqa: F401
        GOMLCustomExtractor,
    )

    _GOML_AVAILABLE = True
except ModuleNotFoundError:
    _GOML_AVAILABLE = False


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.mark.skipif(
    not _GOML_AVAILABLE,
    reason="goml_custom_extractor package not present; endpoint requires AWS (Textract)",
)
def test_extract_txt_returns_200_and_schema(client: TestClient):
    """POST a small text file with LLM processing disabled."""
    response = client.post(
        "/api/idp/extract?process_with_llm=false",
        files={"file": ("sample.txt", b"Hello from integration test.", "text/plain")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "document_id" in data
    assert "file_name" in data
    assert "status" in data
    assert "total_pages" in data
    assert "pages_processed" in data
    assert "pages_data" in data
    assert data["file_name"] == "sample.txt"
    assert data["status"] == "completed"
