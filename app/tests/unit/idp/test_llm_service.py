"""Unit tests for LLMService."""

import pytest
import json
from unittest.mock import patch, AsyncMock

from app.api.schemas.idp.document import (
    ExtractionResponse,
    FileType,
    ProcessingStatus,
    PageData,
)
from app.services.idp.llm_service import LLMService

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockUsage:
    def __init__(self):
        self.prompt_tokens = 10
        self.completion_tokens = 20

class MockChatCompletion:
    def __init__(self, content):
        self.choices = [MockChoice(content)]
        self.usage = MockUsage()

@pytest.fixture
def minimal_extraction_response():
    """Minimal ExtractionResponse for LLM input."""
    return ExtractionResponse(
        document_id="doc-1",
        file_name="test.txt",
        file_type=FileType.TXT,
        status=ProcessingStatus.COMPLETED,
        method="textract",
        total_pages=1,
        pages_processed=1,
        pages_data=[PageData(page_number=1, text_content="Some text")],
        processing_time=0.1,
    )


@pytest.mark.asyncio
async def test_enhance_extraction_returns_llm_result(minimal_extraction_response):
    """enhance_extraction returns the parsed result when acompletion succeeds."""
    with patch("app.services.idp.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = MockChatCompletion('{"key": "value"}')
        service = LLMService()
        result = await service.enhance_extraction(extraction_response=minimal_extraction_response)
        
        assert result == {"key": "value"}
        mock_acompletion.assert_called_once()


@pytest.mark.asyncio
async def test_enhance_extraction_uses_custom_prompt(minimal_extraction_response):
    """When custom_prompt is provided, prompt body contains it."""
    with patch("app.services.idp.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = MockChatCompletion('{"result": "success"}')
        service = LLMService()

        await service.enhance_extraction(
            extraction_response=minimal_extraction_response,
            custom_prompt="Custom instruction",
        )
        
        call_kwargs = mock_acompletion.call_args.kwargs
        messages = call_kwargs.get("messages")
        assert messages is not None
        assert any("Custom instruction" in str(m) for m in messages)


@pytest.mark.asyncio
async def test_enhance_extraction_raises_on_invoker_failure(minimal_extraction_response):
    """When acompletion raises, enhance_extraction propagates the error."""
    with patch("app.services.idp.llm_service.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.side_effect = RuntimeError("LLM error")
        service = LLMService()

        with pytest.raises(RuntimeError) as exc_info:
            await service.enhance_extraction(extraction_response=minimal_extraction_response)
        assert "LLM error" in str(exc_info.value)
