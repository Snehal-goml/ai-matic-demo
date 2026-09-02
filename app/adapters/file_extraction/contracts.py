"""Provider-neutral contracts shared by extraction adapters and the IDP API."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class FileType(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    WORD = "word"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionMethod(str, Enum):
    TEXTRACT = "textract"
    CUSTOM = "custom_extractor"


class PageRange(BaseModel):
    """Page range using one-based, inclusive indexes."""

    start: int = Field(1, ge=1, description="Start page (1-indexed)")
    end: int | None = Field(None, ge=1, description="End page (inclusive, optional)")

    @model_validator(mode="after")
    def validate_range(self) -> "PageRange":
        if self.end is not None and self.end < self.start:
            raise ValueError("end page must be >= start page")
        return self


class ExtractionRequest(BaseModel):
    """Options controlling document extraction and optional enrichment."""

    method: ExtractionMethod = Field(ExtractionMethod.TEXTRACT)
    process_with_llm: bool = Field(True, description="Process with LLM")
    extract_text: bool = Field(True)
    extract_tables: bool = Field(True)
    extract_images: bool = Field(True)
    pages: list[int] | None = Field(None, description="Specific pages to extract (1-indexed)")
    page_range: PageRange | None = Field(None, description="Page range to extract")
    sheets: list[str] | None = Field(None, description="Specific Excel sheets to process")
    process_all: bool = Field(False, description="Process all pages without limit")

    @field_validator("pages")
    @classmethod
    def validate_pages(cls, value: list[int] | None) -> list[int] | None:
        if value is not None:
            if not value:
                raise ValueError("pages list cannot be empty")
            if any(page < 1 for page in value):
                raise ValueError("page numbers must be >= 1")
        return value


class TableInfo(BaseModel):
    table_id: str
    page_number: int
    headers: list[str]
    rows: list[list[str]]
    confidence: float | None = None

    @field_validator("rows", mode="before")
    @classmethod
    def validate_rows(cls, value: list[list[Any]] | None) -> list[list[str]]:
        if value is None:
            return []
        return [[str(cell) if cell is not None else "" for cell in row] for row in value]

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: list[Any] | None) -> list[str]:
        if value is None:
            return []
        return [str(header) if header is not None else "" for header in value]


class ImageInfo(BaseModel):
    image_id: str
    file_path: str
    page_number: int
    format: str
    width: int | None = None
    height: int | None = None


class FormField(BaseModel):
    key: str
    value: str
    confidence: float | None = None


class PageData(BaseModel):
    page_number: int
    text_content: str = ""
    tables: list[TableInfo] = Field(default_factory=list)
    images: list[ImageInfo] = Field(default_factory=list)
    forms: list[FormField] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionResponse(BaseModel):
    """Normalized output returned by every extraction adapter."""

    document_id: str
    file_name: str
    file_type: FileType
    status: ProcessingStatus
    method: ExtractionMethod
    total_pages: int
    pages_processed: int
    pages_data: list[PageData] = Field(default_factory=list)
    llm_output: dict[str, Any] | None = None
    processing_time: float
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    s3_key: str | None = None
    textract_job_id: str | None = None


class TextractJobStatus(BaseModel):
    job_id: str
    status: ProcessingStatus
    document_id: str
    progress: float | None = None
    result: ExtractionResponse | None = None
