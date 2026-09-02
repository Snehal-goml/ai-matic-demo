# goML's Intelligent Data Processing Boilerplate

A production-ready, highly configurable FastAPI service for extracting structured data from documents. This boilerplate provides a flexible foundation that can be easily customized to meet your specific document processing needs.

---

## How you can consume this project

When integrating or deploying this codebase, you can combine **extraction** and **LLM** choices as follows.

### Extraction options (choose one per deployment)

| Option | Configuration | Use case |
|--------|----------------|----------|
| **1. Custom extractor + AWS Textract** | Run two instances (or switch `EXTRACTOR_TYPE` per environment): one with `EXTRACTOR_TYPE=AWS_textract`, one with `EXTRACTOR_TYPE=goml_custom_extractor`. Route traffic by file type or environment. | Use Textract for PDFs/images where you need AWS OCR; use custom extractor for Excel, Word, CSV, or when avoiding AWS. |
| **2. AWS Textract alone** | `EXTRACTOR_TYPE=AWS_textract`. Set `BUCKET_NAME` (and AWS credentials). | Production-scale OCR and layout; best accuracy for scanned PDFs and images; requires S3 and Textract. |
| **3. Custom extractor alone** | `EXTRACTOR_TYPE=goml_custom_extractor`. No AWS required for extraction. | Local/offline extraction using pdfplumber, PyMuPDF, python-docx, pandas, pytesseract; no AWS dependency for extraction. |

### LLM options (choose one per deployment)

| Option | Configuration | Use case |
|--------|----------------|----------|
| **1. Bedrock** | `LLM_PROVIDER=bedrock`. Set `MODEL_ID` (e.g. Claude) and AWS credentials. | Use AWS Bedrock (e.g. Claude) for LLM enhancement; keeps everything in AWS. |
| **2. OpenAI** | `LLM_PROVIDER=openai`. Set `OPENAI_API_KEY` and `OPENAI_MODEL`. | Use OpenAI (e.g. GPT-4) for LLM enhancement; no Bedrock required. |
| **3. Both** | Run two instances (or switch `LLM_PROVIDER` per environment): one `bedrock`, one `openai`. | Support different backends for different environments or A/B testing; one provider per process. |

**Summary:** One **extractor** and one **LLM provider** per process. For multiple combinations (e.g. Textract + custom, or Bedrock + OpenAI), run multiple instances or use different `.env` per environment.

---

## How to consume this project (developers)

**New to this repo?** See **[docs/DEVELOPER_CONSUMPTION.md](docs/DEVELOPER_CONSUMPTION.md)** for:

- Prerequisites and one-command run (local or Docker)
- How to call the API (curl examples, auth, custom output format)
- Configuration at a glance and where to look next
- **Component tiers**: how to reuse only parts of the project (Tier 1 = drop-in, Tier 2 = replace folder/file, Tier 3 = project-specific)

---

## Quick start

```bash
git clone <repository-url>
cd structured_document_processing
cp .env.example .env
# Edit .env and set at least EXTRACTOR_TYPE (and BUCKET_NAME/MODEL_ID if using AWS)
pip install -r requirements.txt
make run
# Or: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **OpenAPI spec**: `http://localhost:8000/openapi.json`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Overview

This boilerplate supports multiple document types (PDF, images, DOCX, Excel, CSV, TXT) and offers two interchangeable extraction pipelines:

- **Textract Pipeline**: Uses AWS Textract for OCR and structure detection, with optional post-processing via an LLM (Bedrock or OpenAI) to produce structured output
- **Custom Extractor Pipeline**: Local, library-based extraction using open-source tools (pdfplumber, PyMuPDF, pandas, python-docx, pytesseract) producing a unified, typed response

---

## Service architecture

High-level flow: the API delegates to **Extraction Service**, which uses **Extractor Factory** (one of AWS Textract or Custom extractor) and optionally **LLM Service**, which uses **LLM Factory** (Bedrock or OpenAI).

```mermaid
flowchart LR
    subgraph Client
        C[Client]
    end
    subgraph API
        API[API /api/v1/extract]
    end
    subgraph Orchestration
        ES[Extraction Service]
    end
    subgraph Extraction
        EF[Extractor Factory]
        T[AWSTextractExtractor]
        G[GOML Custom Extractor]
    end
    subgraph LLM
        LS[LLM Service]
        LF[LLM Factory]
        BD[Bedrock Invoker]
        OI[OpenAI Invoker]
    end
    subgraph External
        S3[(S3)]
        TAPI[AWS Textract]
        BR[(Bedrock)]
        OAPI[OpenAI API]
    end

    C -->|POST /extract| API
    API --> ES
    ES --> EF
    EF -->|EXTRACTOR_TYPE=AWS_textract| T
    EF -->|EXTRACTOR_TYPE=goml_custom_extractor| G
    T --> S3
    T --> TAPI
    ES -->|optional process_with_llm| LS
    LS --> LF
    LF -->|LLM_PROVIDER=bedrock| BD
    LF -->|LLM_PROVIDER=openai| OI
    BD --> BR
    OI --> OAPI
    ES -->|ExtractionResponse| API
    API --> C
```

### Component summary

| Layer | Component | Role |
|-------|-----------|------|
| **API** | `app/main.py` | FastAPI app, middleware, Mangum Lambda handler |
| **API** | `app/api/v1/endpoints/extraction.py` | Extract, batch, health endpoints |
| **Orchestration** | `app/services/extraction_service.py` | Orchestrates extractor + optional LLM |
| **Extraction** | `app/core/factory.py` | ExtractorFactory → AWS_textract or goml_custom_extractor |
| **Extraction** | `app/core/aws_textract/` | AWSTextractExtractor (S3 + Textract) |
| **Extraction** | `app/core/custom_extractor/` or `custom_extractor01/` | GOMLCustomExtractor (PDF, Excel, Word, CSV, image, text) |
| **LLM** | `app/services/llm_service.py` | Enhance extraction; uses LLMFactory |
| **LLM** | `app/core/llm_factory.py` | LLMFactory → Bedrock or OpenAI invoker |
| **LLM** | `app/core/bedrock/`, `app/core/openai/` | BedrockInvoker, OpenAIInvoker |
| **Config** | `app/config/settings.py` | Env-driven settings (EXTRACTOR_TYPE, LLM_PROVIDER, etc.) |
| **Adapters** | `app/adapters/aws_clients.py` | Singleton AWS clients (Textract, S3, Bedrock Runtime) |

For more detail, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/ARCHITECTURE_DIAGRAM.md](docs/ARCHITECTURE_DIAGRAM.md).

---

## Key Features

- 🎯 **Highly Configurable**: Easy-to-customize settings for all aspects of document processing
- 🔄 **Dual Extraction Methods**: Switch between AWS Textract and local extractors seamlessly
- 🤖 **LLM Integration**: Optional AI-powered enhancement via AWS Bedrock (Claude) or OpenAI (e.g. GPT-4); choose provider with `LLM_PROVIDER`
- 📦 **Custom Output Formats**: Define your own JSON output structure for extracted data
- 🎨 **Custom Prompts**: Modify LLM prompts to match your specific use case
- ⚡ **Production Ready**: Built with FastAPI, ready for Lambda deployment via Mangum
- 🔧 **Extensible Architecture**: Easy to add new extractors, file types, or processing steps

---

## Configuration Guide

The boilerplate is designed with configuration-first principles, making it easy to adapt to your needs without modifying core code.

### 1. Environment Configuration

All configuration is managed through environment variables and the `app/config/settings.py` file.

#### Required Environment Variables

Create a `.env` file at the repository root:

```bash
# AWS Configuration
AWS_REGION=us-east-1
BUCKET_NAME=your-s3-bucket-name
MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0

# AWS Credentials (or use IAM roles/instance profiles)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

#### Configurable Settings

All settings are defined in `app/config/settings.py` and can be customized:

```python
# File Processing Limits
MAX_FILE_SIZE_MB: int = 100          # Maximum file size in MB
MAX_PAGES_PER_REQUEST: int = 50      # Maximum pages to process per request
CHUNK_SIZE_MB: int = 10              # Chunk size for large file processing

# Timeouts (seconds)
TEXTRACT_TIMEOUT: int = 300           # AWS Textract operation timeout
LLM_TIMEOUT: int = 60                 # LLM processing timeout
FILE_UPLOAD_TIMEOUT: int = 120        # File upload timeout

# Concurrency
MAX_WORKERS: int = 4                  # Maximum worker threads
MAX_CONCURRENT_PAGES: int = 5         # Maximum concurrent page processing

# S3 Configuration
S3_PREFIX: str = "document-uploads"  # S3 key prefix for uploaded files
S3_TEMP_EXPIRY_DAYS: int = 1         # Temporary file retention period

# Retry Configuration
MAX_RETRIES: int = 3                  # Maximum retry attempts
RETRY_DELAY: float = 1.0              # Delay between retries (seconds)
```

**To customize these values**, you can:

1. **Override via environment variables**: Set `MAX_FILE_SIZE_MB=200` in your `.env` file
2. **Modify `app/config/settings.py`**: Change default values directly
3. **Use different settings per environment**: Create environment-specific `.env` files

### 2. Custom Output Format Configuration

The boilerplate allows you to define custom JSON output structures for extracted data.

#### Default Output Format

The default format is defined in `app/config/output_format.json`:

```json
{
  "document_type": "Invoice/Receipt/Form/Contract/Report/Medical Record/etc.",
  "extracted_fields": {
    "description": "All key-value pairs found in the document",
    "fields": {}
  },
  "tables": [
    {
      "table_name": "string",
      "headers": ["column1", "column2"],
      "rows": [
        ["value1", "value2"]
      ]
    }
  ],
  "summary": "Brief description of document content",
  "metadata": {
    "total_fields_extracted": 0,
    "confidence": 0.0
  }
}
```

#### Customizing Output Format

**Option 1: Modify the default format file**

Edit `app/config/output_format.json` to match your desired structure:

```json
{
  "invoice_number": "",
  "date": "",
  "vendor": {
    "name": "",
    "address": "",
    "tax_id": ""
  },
  "line_items": [
    {
      "description": "",
      "quantity": 0,
      "unit_price": 0.0,
      "total": 0.0
    }
  ],
  "totals": {
    "subtotal": 0.0,
    "tax": 0.0,
    "total": 0.0
  }
}
```

**Option 2: Pass custom format via API**

When calling the extraction endpoint, pass a `custom_output_format` parameter:

```bash
curl -X POST "http://localhost:8000/api/v1/extract?process_with_llm=true" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F "custom_output_format={\"invoice_number\":\"\",\"date\":\"\",\"amount\":0.0}"
```

The LLM will use your custom format to structure the extracted data.

### 3. Custom Prompt Configuration

The LLM prompts are defined in `app/prompts/rjfs_prompt.py`. You can customize these to:

- Change extraction instructions
- Modify output format requirements
- Add domain-specific rules
- Adjust field extraction logic

#### Key Prompt Functions

- `build_key_value_extraction_prompt()`: Generates prompts for key-value pair extraction
- `build_claude_prompt()`: Creates prompts for RJSF schema generation
- `build_claude_prompt_image()`: Image-based schema generation prompts
- `handle_other()`: Handles "Other" option fields in forms

**Example: Customizing extraction instructions**

Edit `app/prompts/rjfs_prompt.py`:

```python
def build_key_value_extraction_prompt(...):
    instruction = f"""You are a document data extraction specialist for medical records.

    SPECIAL INSTRUCTIONS FOR MEDICAL DOCUMENTS:
    1. Preserve all medical terminology exactly as written
    2. Extract patient identifiers with high confidence
    3. Flag any missing required fields

    {format_instruction}
    ...
    """
```

### 4. AWS Client Configuration

AWS clients are configured in `app/clients/aws_clients.py`. You can customize:

- **Region settings**: Modify `region_name` in client initialization
- **Timeout settings**: Adjust `read_timeout` and `connect_timeout` in `boto_config`
- **Retry behavior**: Modify retry configuration in `boto_config`

**Example: Customizing AWS client timeouts**

```python
# In app/clients/aws_clients.py
boto_config = Config(
    read_timeout=300,        # Increase for large documents
    connect_timeout=20,       # Increase connection timeout
    retries={
        'max_attempts': 5,    # More retry attempts
        'mode': 'adaptive'
    }
)
```

### 5. Extraction Method Configuration

You can customize which extraction method is used for different file types.

**In `app/api/v1/endpoints/extraction.py`**, the auto-selection logic can be modified:

```python
# Current auto-selection
if file_type in [FileType.EXCEL, FileType.CSV]:
    method = ExtractionMethod.CUSTOM
elif file_type in [FileType.WORD, FileType.DOCX]:
    method = ExtractionMethod.CUSTOM
elif file_type == FileType.PDF and method == ExtractionMethod.TEXTRACT:
    pass  # Keep Textract for PDFs

# Customize: Force custom extractor for all PDFs
if file_type == FileType.PDF:
    method = ExtractionMethod.CUSTOM
```

### 6. File Type Support Configuration

Add support for new file types by:

1. **Adding file type enum** in `app/api/v1/schemas/schema.py`:

```python
class FileType(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    WORD = "word"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"
    # Add your custom type
    CUSTOM_TYPE = "custom_type"
```

2. **Adding extractor** in `app/core/extractors/` or `app/core/custom_extractor/`
3. **Updating file detection** in `app/utils/file_utils.py`

### 7. LLM provider and model configuration

Choose LLM backend with `LLM_PROVIDER` and set the matching variables.

**Bedrock** (`LLM_PROVIDER=bedrock`):

```bash
LLM_PROVIDER=bedrock
MODEL_ID=us.anthropic.claude-3-5-sonnet-20241022-v2:0
# Or: anthropic.claude-3-opus-20240229-v1:0, anthropic.claude-3-haiku-20240229-v1:0
```

**OpenAI** (`LLM_PROVIDER=openai`):

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o
```

### 8. Processing Options Configuration

Customize processing behavior via API parameters:

- `extract_text`: Enable/disable text extraction
- `extract_tables`: Enable/disable table extraction
- `extract_images`: Enable/disable image extraction
- `process_with_llm`: Enable/disable LLM enhancement
- `pages`: Specify specific pages to process
- `page_range_start` / `page_range_end`: Process page ranges
- `sheets`: For Excel files, specify which sheets to process

---

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd structured_document_processing

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file:

```bash
AWS_REGION=us-east-1
BUCKET_NAME=your-s3-bucket
MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0
```

### 3. Run Locally

```bash
# Using uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or using the run script
python run.py
```

API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Customization Examples

### Example 1: Custom Invoice Extraction Format

1. **Create custom format** in `app/config/output_format.json`:

```json
{
  "invoice": {
    "number": "",
    "date": "",
    "due_date": ""
  },
  "vendor": {
    "name": "",
    "address": "",
    "contact": ""
  },
  "items": [
    {
      "description": "",
      "quantity": 0,
      "price": 0.0
    }
  ],
  "totals": {
    "subtotal": 0.0,
    "tax": 0.0,
    "total": 0.0
  }
}
```

2. **Use in API call**:

```bash
curl -X POST "http://localhost:8000/api/v1/extract" \
  -F "file=@invoice.pdf" \
  -F "custom_output_format=$(cat app/config/output_format.json)"
```

### Example 2: Custom Medical Form Prompts

1. **Modify prompts** in `app/prompts/rjfs_prompt.py`:

```python
instruction = f"""You are extracting data from medical intake forms.

MEDICAL FORM RULES:
- Preserve all medical terminology exactly
- Extract patient demographics with high accuracy
- Flag any missing required medical fields
- Maintain HIPAA compliance in field naming

{format_instruction}
...
"""
```

### Example 3: Adjust Processing Limits

1. **Modify settings** in `app/config/settings.py`:

```python
MAX_FILE_SIZE_MB: int = 500  # Allow larger files
MAX_PAGES_PER_REQUEST: int = 100  # Process more pages
MAX_CONCURRENT_PAGES: int = 10  # More parallel processing
```

Or via environment variables:

```bash
MAX_FILE_SIZE_MB=500
MAX_PAGES_PER_REQUEST=100
MAX_CONCURRENT_PAGES=10
```

---

## API Usage

### Basic Extraction

```bash
curl -X POST "http://localhost:8000/api/v1/extract" \
  -F "file=@document.pdf"
```

### With Custom Output Format

```bash
curl -X POST "http://localhost:8000/api/v1/extract?process_with_llm=true" \
  -F "file=@document.pdf" \
  -F "custom_output_format={\"field1\":\"\",\"field2\":0}"
```

### Specific Pages Only

```bash
curl -X POST "http://localhost:8000/api/v1/extract?pages=1,3,5" \
  -F "file=@document.pdf"
```

### Page Range

```bash
curl -X POST "http://localhost:8000/api/v1/extract?page_range_start=1&page_range_end=10" \
  -F "file=@document.pdf"
```

### Custom Extractor Method

```bash
curl -X POST "http://localhost:8000/api/v1/extract?method=custom_extractor" \
  -F "file=@document.pdf"
```

---

## Project structure

```
app/
├── main.py                       # FastAPI app, middleware, Lambda handler
├── config/
│   ├── settings.py               # All env configuration (CUSTOMIZE HERE)
│   └── output_format.json        # Default output format (CUSTOMIZE HERE)
├── api/
│   ├── rate_limit.py             # Optional rate limiting
│   └── v1/
│       ├── endpoints/
│       │   └── extraction.py     # Extract, batch, health
│       └── schemas/
│           └── schema.py        # Data models
├── core/
│   ├── base.py                   # BaseExtractor interface
│   ├── factory.py                # Extractor factory (EXTRACTOR_TYPE)
│   ├── llm_factory.py            # LLM factory (LLM_PROVIDER → bedrock | openai)
│   ├── aws_textract/             # AWS Textract + S3 pipeline
│   ├── bedrock/                  # BedrockInvoker for Bedrock LLM
│   ├── openai/                   # OpenAIInvoker for OpenAI LLM
│   └── custom_extractor/         # GOML local extraction (PDF, Excel, etc.)
│       or custom_extractor01/    # (implementation may live in either)
├── services/
│   ├── extraction_service.py     # Orchestrates extractor + optional LLM
│   └── llm_service.py            # LLM enhancement; uses LLMFactory
├── adapters/
│   └── aws_clients.py            # AWS clients singleton (CUSTOMIZE HERE)
├── prompts/
│   ├── rjfs_prompt.py            # LLM prompts (CUSTOMIZE HERE)
│   └── version_loader.py         # Prompt version resolution
└── utils/                        # Logging, file_utils, s3, bedrock
```

**To add a new extractor**: implement `BaseExtractor` in a new module under `core/`, then register it in `app/core/factory.py`. **To add a new LLM provider**: implement an invoker with the same interface as `BedrockInvoker`/`OpenAIInvoker` and register it in `app/core/llm_factory.py`.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EXTRACTOR_TYPE` | No (default: `AWS_textract`) | `AWS_textract` or `goml_custom_extractor` |
| `BUCKET_NAME` | When `EXTRACTOR_TYPE=AWS_textract` | S3 bucket for Textract input |
| `LLM_PROVIDER` | No (default: `bedrock`) | `bedrock` or `openai` — which LLM to use for enhancement |
| `MODEL_ID` | When `LLM_PROVIDER=bedrock` | Bedrock model id (e.g. Claude) |
| `OPENAI_API_KEY` | When `LLM_PROVIDER=openai` | OpenAI API key |
| `OPENAI_MODEL` | When `LLM_PROVIDER=openai` | OpenAI model (e.g. `gpt-4o`) |
| `AWS_REGION` | No | AWS region (default `us-east-1`) |
| `AUTH_METHOD` | No | `none`, `api_key`, `bearer`, `jwt` |
| `API_KEY` / `API_KEYS` | When api_key | Single key or comma-separated list |
| `LOG_LEVEL`, `LOG_FORMAT` | No | Logging (LOG_FORMAT: `text` or `json`) |
| `ENV` | No | `development` / `production` |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_PER_MINUTE` | No | Optional rate limiting |
| `HEALTH_CHECK_S3`, `HEALTH_CHECK_BEDROCK` | No | Enable in readiness |
| `MAX_BATCH_FILES` | No | Max files per batch (default 10) |

See `.env.example` for a full list and short comments.

## Extractor and LLM selection

- **EXTRACTOR_TYPE=AWS_textract**: Use for production-scale OCR and layout; requires S3 and AWS Textract. Set `BUCKET_NAME`; set `MODEL_ID` if using Bedrock for LLM.
- **EXTRACTOR_TYPE=goml_custom_extractor**: Use for local development or when avoiding AWS; supports PDF, Excel, Word, CSV, images, text via local libraries (pdfplumber, PyMuPDF, etc.).
- **LLM_PROVIDER=bedrock**: Use AWS Bedrock (e.g. Claude) for LLM enhancement; set `MODEL_ID`.
- **LLM_PROVIDER=openai**: Use OpenAI for LLM enhancement; set `OPENAI_API_KEY` and `OPENAI_MODEL`.

---

## Deployment

- **Lambda**: Use the provided Dockerfile; handler is `app.main.handler`. Configure via API Gateway or ALB; ensure the Lambda role has Textract, Bedrock, and S3 permissions. No lifespan or graceful shutdown in Lambda.
- **Docker**: Build the server image and run uvicorn: `docker build -f Dockerfile.server -t app . && docker run -p 8000:8000 --env-file .env app`
- **Docker Compose**: `make docker-up` (or `docker-compose up -d`). Uses `Dockerfile.server`, port 8000, env from `.env`. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) and CI config if present.

## Enabling API security

Set `AUTH_METHOD` in `.env`:

- **api_key**: Set `API_KEY` or `API_KEYS` (comma-separated). Clients send `X-API-Key`.
- **bearer**: Set `BEARER_TOKEN`. Clients send `Authorization: Bearer <token>`.
- **jwt**: Set `JWT_SECRET` and optionally `JWT_ALGORITHM`. Clients send `Authorization: Bearer <jwt>`.

Health and `/docs`, `/openapi.json` remain unauthenticated. For production, store secrets in AWS Secrets Manager or SSM (see `docs/SECRETS.md` if present).

## Running tests

```bash
pip install -r requirements.txt
make test
# Or: pytest
```

Lint and format: `make lint`, `make format` (ruff).

---

## Requirements

- Python 3.11+
- AWS account with Textract and Bedrock access
- AWS credentials (via environment, IAM role, or credentials file)
- Optional: Tesseract OCR (for custom image extraction)

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to run tests, lint, submit PRs, and add extractors or file types.

---

## License

MIT. See [LICENSE](docs/LICENSE).

---

## Support

For customization help or questions:
- Review the configuration sections above
- Check `app/config/settings.py` for all available options
- Examine example customizations in the prompts and extractors

---

**Remember**: This is a boilerplate designed for easy customization. Most changes can be made through configuration files without touching core logic!
