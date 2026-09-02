import logging
import uuid
from typing import Any

from app.adapters.file_extraction.factory import ExtractorFactory
from app.api.schemas.idp.document import (
    ExtractionRequest,
    ExtractionResponse,
    FileType,
    ProcessingStatus,
)
from app.services.idp.llm_service import LLMService

logger = logging.getLogger(__name__)


class ExtractionService:
    """Orchestrate document extraction and optional LLM enhancement."""

    def __init__(
        self,
        *,
        extractor: Any = None,
        llm_service: LLMService | None = None,
    ) -> None:
        self.extractor = extractor or ExtractorFactory.create()
        self.llm_service = llm_service or LLMService()
        logger.info(
            f"ExtractionService initialized with extractor: {self.extractor.get_extractor_name()}"
        )

    async def process_document(
        self,
        file_path: str,
        file_bytes: bytes,
        file_name: str,
        file_type: FileType,
        request: ExtractionRequest,
        document_id: str | None = None,
        custom_prompt: str | None = None,
        custom_output_format: dict[str, Any] | None = None,
        prompt_version: str | None = None,
    ) -> ExtractionResponse:
        """Extract a document and optionally enrich the result through the model gateway."""

        if document_id is None:
            document_id = str(uuid.uuid4())

        logger.info(
            f"Processing document {document_id}: {file_name} ({file_type}) "
            f"with extractor: {self.extractor.get_extractor_name()}"
        )

        try:
            extraction_response = await self.extractor.extract(
                file_path=file_path,
                file_bytes=file_bytes,
                file_name=file_name,
                file_type=file_type,
                request=request,
                document_id=document_id,
            )

            if request.process_with_llm and extraction_response.pages_data:
                try:
                    logger.info(f"Enhancing extraction with LLM: {document_id}")
                    llm_output = await self.llm_service.enhance_extraction(
                        extraction_response=extraction_response,
                        custom_prompt=custom_prompt,
                        custom_output_format=custom_output_format,
                        prompt_version=prompt_version,
                    )
                    extraction_response.llm_output = llm_output
                    if custom_output_format:
                        extraction_response.metadata["custom_format_used"] = True
                    logger.info(f"LLM enhancement completed: {document_id}")

                except Exception as llm_error:
                    logger.error(f"LLM enhancement failed: {str(llm_error)}")
                    extraction_response.status = ProcessingStatus.FAILED
                    extraction_response.error_message = f"LLM processing failed: {str(llm_error)}"

            return extraction_response

        except Exception as e:
            logger.error(f"Document processing failed: {str(e)}")
            raise
