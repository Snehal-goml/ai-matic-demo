"""Factory to create the configured extractor from settings.

Composition root for extractors. AWSTextractExtractor self-creates its
Textract/S3 clients when none are injected; tests may pass mocks via
AWSTextractExtractor(textract_client=..., s3_manager=...).
"""

from app.config.settings import get_settings


class ExtractorFactory:
    """Creates the configured extractor based on EXTRACTOR_TYPE."""

    @staticmethod
    def create():
        """Create and return the extractor instance based on EXTRACTOR_TYPE."""
        settings = get_settings()
        if settings.EXTRACTOR_TYPE == "goml_custom_extractor":
            try:
                from app.adapters.file_extraction.extractors.custom_extractor.extractor import (
                    GOMLCustomExtractor,
                )
            except ModuleNotFoundError as exc:
                raise ValueError(
                    "goml_custom_extractor is configured (EXTRACTOR_TYPE) but the "
                    "app.adapters.file_extraction.extractors.custom_extractor package "
                    "is not present in this deployment. Use EXTRACTOR_TYPE=AWS_textract."
                ) from exc

            return GOMLCustomExtractor(
                max_pages=settings.MAX_PAGES_PER_REQUEST,
                max_workers=settings.MAX_WORKERS,
                max_concurrent_pages=settings.MAX_CONCURRENT_PAGES,
            )
        if settings.EXTRACTOR_TYPE == "AWS_textract":
            from app.adapters.file_extraction.extractors.textract.extractor import (
                AWSTextractExtractor,
            )

            return AWSTextractExtractor(
                region=settings.AWS_REGION,
                bucket_name=settings.BUCKET_NAME,
                s3_prefix=settings.S3_PREFIX,
                textract_timeout=settings.TEXTRACT_TIMEOUT,
                temp_expiry_days=settings.S3_TEMP_EXPIRY_DAYS,
            )
        raise ValueError(f"Unknown EXTRACTOR_TYPE: {settings.EXTRACTOR_TYPE}")
