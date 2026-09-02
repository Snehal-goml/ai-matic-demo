"""IDP feature registration."""

import asyncio
import logging

from fastapi import APIRouter

from app.adapters.file_extraction.factory import ExtractorFactory
from app.api.endpoints.idp import ingestion
from app.config.settings import get_settings
from app.core.feature_contract import FeatureModule

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(ingestion.router)

SUPPORTED_EXTRACTOR_TYPES = ("AWS_textract", "goml_custom_extractor")


def _validate_config() -> None:
    settings = get_settings()
    if settings.EXTRACTOR_TYPE not in SUPPORTED_EXTRACTOR_TYPES:
        message = (
            f"EXTRACTOR_TYPE must be one of {SUPPORTED_EXTRACTOR_TYPES}, "
            f"got: {settings.EXTRACTOR_TYPE}"
        )
        logger.error(message)
        raise ValueError(message)
    if settings.EXTRACTOR_TYPE == "AWS_textract" and not settings.BUCKET_NAME.strip():
        message = "BUCKET_NAME is required when EXTRACTOR_TYPE=AWS_textract"
        logger.error(message)
        raise ValueError(message)


def _check_extractor() -> str:
    ExtractorFactory.create()
    return "ok"


async def _check_s3() -> str:
    settings = get_settings()
    if not settings.HEALTH_CHECK_S3:
        return "disabled"
    if not settings.BUCKET_NAME:
        raise RuntimeError("BUCKET_NAME is required for the S3 health check")

    def head_bucket() -> None:
        from app.utils.s3_utils import create_s3_client

        create_s3_client().head_bucket(Bucket=settings.BUCKET_NAME)

    await asyncio.to_thread(head_bucket)
    return "ok"


FEATURE = FeatureModule(
    slug="idp",
    router=router,
    prefix="/api/idp",
    tags=["IDP"],
    health_checks={
        "extractor": _check_extractor,
        "s3": _check_s3,
    },
    on_startup=_validate_config,
)
