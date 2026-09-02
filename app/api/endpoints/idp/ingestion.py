import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.api.dependencies.auth import get_optional_auth
from app.api.dependencies.rate_limit import limiter, rate_limit_string
from app.api.schemas.idp.document import (
    ExtractionMethod,
    ExtractionRequest,
    ExtractionResponse,
    FileType,
    PageRange,
)
from app.services.idp.ingestion_service import ExtractionService
from app.utils.idp.file_utils import FileValidator, TempFileManager

logger = logging.getLogger(__name__)
router = APIRouter()


# Lazy initialization of services via dependency injection
def get_extraction_service() -> ExtractionService:
    """Get or create extraction service (dependency injection)."""
    return ExtractionService()


@router.post(
    "/extract",
    response_model=ExtractionResponse,
    tags=["Document Ingestion"],
    summary="Extract data from uploaded document",
)
@limiter.limit(rate_limit_string)
async def extract_document(
    request: Request,
    file: UploadFile = File(
        ...,
        description="Document file to process.",
    ),
    method: ExtractionMethod = ExtractionMethod.TEXTRACT,
    process_with_llm: bool = True,
    _auth: Any | None = Depends(get_optional_auth),
    extraction_service: ExtractionService = Depends(get_extraction_service),
    extract_text: bool = True,
    extract_tables: bool = True,
    extract_images: bool = True,
    pages: str | None = None,
    page_range_start: int | None = None,
    page_range_end: int | None = None,
    sheets: str | None = None,
    process_all: bool = False,
    custom_prompt: str | None = None,
    custom_output_format: str | None = None,
    prompt_version: str | None = None,
):
    temp_file_path = None

    try:
        from app.config.settings import get_settings

        settings = get_settings()
        if settings.ALLOWED_UPLOAD_CONTENT_TYPES:
            allowed = [
                s.strip().lower()
                for s in settings.ALLOWED_UPLOAD_CONTENT_TYPES.split(",")
                if s.strip()
            ]
            ct = (file.content_type or "").strip().lower()
            if ct and allowed and ct not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Content-Type '{file.content_type}' not allowed. Allowed: {allowed}",
                )

        logger.info(f"Validating file: {file.filename}")
        file_size = await FileValidator.validate_file_size(file)

        logger.info(f"Reading file: {file.filename} ({file_size / 1024 / 1024:.2f}MB)")
        file_bytes = await file.read()

        file_type = await FileValidator.detect_file_type(file, file_bytes)
        logger.info(f"Detected file type: {file_type}")

        await file.seek(0)

        if file_type in [
            FileType.PDF,
            FileType.EXCEL,
            FileType.WORD,
            FileType.DOCX,
            FileType.IMAGE,
            FileType.CSV,
        ]:
            temp_file_path = await TempFileManager.save_upload_to_temp(file, file_type)
            logger.info(f"Saved to temp: {temp_file_path}")

        custom_format_dict: dict[str, Any] | None = None
        if custom_output_format:
            try:
                if isinstance(custom_output_format, str):
                    custom_format_dict = json.loads(custom_output_format)
                elif isinstance(custom_output_format, dict):
                    custom_format_dict = custom_output_format
                else:
                    raise ValueError("custom_output_format must be a JSON string or dict")

                if not isinstance(custom_format_dict, dict):
                    raise ValueError(
                        "custom_output_format must be a JSON object (dict), not an array or primitive"
                    )

                logger.info("Custom output format provided and parsed successfully as JSON")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse custom output format: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid custom output format JSON: {str(e)}. Must be a valid JSON object.",
                )

        request_obj = _build_extraction_request(
            method=method,
            process_with_llm=process_with_llm,
            extract_text=extract_text,
            extract_tables=extract_tables,
            extract_images=extract_images,
            pages=pages,
            page_range_start=page_range_start,
            page_range_end=page_range_end,
            sheets=sheets,
            process_all=process_all,
        )

        logger.info(f"Starting extraction: {file.filename}")

        response = await extraction_service.process_document(
            file_path=temp_file_path or "",
            file_bytes=file_bytes,
            file_name=file.filename or "unknown",
            file_type=file_type,
            request=request_obj,
            custom_prompt=custom_prompt,
            custom_output_format=custom_format_dict,
            prompt_version=prompt_version,
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")

    finally:
        if temp_file_path:
            await TempFileManager.cleanup_temp_file(temp_file_path)


def _build_extraction_request(
    method: ExtractionMethod,
    process_with_llm: bool,
    extract_text: bool,
    extract_tables: bool,
    extract_images: bool,
    pages: str | None,
    page_range_start: int | None,
    page_range_end: int | None,
    sheets: str | None,
    process_all: bool = False,
) -> ExtractionRequest:
    pages_list = None
    if pages:
        try:
            pages_list = [int(p.strip()) for p in pages.split(",")]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid pages parameter. Must be comma-separated integers (e.g., '1,3,5')",
            )

    page_range_obj = None
    if page_range_start is not None:
        page_range_obj = PageRange(start=page_range_start, end=page_range_end)

    sheets_list = None
    if sheets:
        sheets_list = [s.strip() for s in sheets.split(",")]

    return ExtractionRequest(
        method=method,
        process_with_llm=process_with_llm,
        extract_text=extract_text,
        extract_tables=extract_tables,
        extract_images=extract_images,
        pages=pages_list,
        page_range=page_range_obj,
        sheets=sheets_list,
        process_all=process_all,
    )


@router.post(
    "/extract/batch",
    response_model=list[ExtractionResponse],
    tags=["Document Ingestion"],
    summary="Extract data from multiple documents",
)
@limiter.limit(rate_limit_string)
async def extract_multiple_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    method: ExtractionMethod = ExtractionMethod.TEXTRACT,
    process_with_llm: bool = True,
    _auth: Any | None = Depends(get_optional_auth),
):
    from app.config.settings import get_settings

    max_batch = get_settings().MAX_BATCH_FILES
    if len(files) > max_batch:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {max_batch} files per batch request; received {len(files)}",
        )

    import asyncio

    tasks = []
    for file in files:
        task = extract_document(
            request=request, file=file, method=method, process_with_llm=process_with_llm
        )
        tasks.append(task)

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        responses = []
        failures = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"File {idx} processing failed: {str(result)}")
                failures.append(
                    {
                        "index": idx,
                        "file_name": files[idx].filename,
                        "error": str(result),
                    }
                )
            else:
                responses.append(result)
        if failures:
            raise HTTPException(
                status_code=500,
                detail={"message": "One or more files failed processing", "failures": failures},
            )
        return responses

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch processing failed: {str(e)}")
