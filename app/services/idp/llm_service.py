import asyncio
import json
import logging
from typing import Any

from app.api.schemas.idp.document import ExtractionResponse
from app.config.settings import settings
from app.core.model_gateway.aim_main import acompletion
from app.core.prompts.idp.loader import get_prompt_builder

logger = logging.getLogger(__name__)

# Optional in-memory token counter for metrics (no PII)
_llm_tokens_total: list[int] = [0]


def _parse_gateway_response(response: Any) -> dict[str, Any]:
    """Parse the gateway's OpenAI-compatible response without masking shape errors."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("Model gateway returned an invalid completion response") from exc

    if not isinstance(content, str):
        raise RuntimeError("Model gateway completion content must be a string")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {"result": content}
    return parsed if isinstance(parsed, dict) else {"result": parsed}


class LLMService:
    """Service for processing extracted data with LLM (supports multiple providers via model gateway)"""

    def __init__(self):
        logger.info(f"LLMService initialized with gateway provider: {settings.LLM_PROVIDER}")

    async def enhance_extraction(
        self,
        extraction_response: ExtractionResponse,
        custom_prompt: str = None,
        custom_output_format: dict[str, Any] | None = None,
        prompt_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Process extraction results with LLM to get structured key-value output

        Args:
            extraction_response: The extraction results
            custom_prompt: Optional custom prompt to override default
            custom_output_format: Optional custom JSON structure for output
            prompt_version: Optional prompt version id (e.g. default, v1)
        """
        try:
            version_used = prompt_version or "default"
            logger.info(
                f"Enhancing extraction with LLM: {extraction_response.document_id}, prompt_version={version_used}"
            )

            if custom_output_format:
                logger.info("Using custom output format provided by user")

            prompt_body = self._build_prompt_request(
                extraction_response,
                custom_prompt,
                custom_output_format,
                prompt_version=prompt_version,
            )

            # Extract generic parameters from prompt_body if available
            messages = prompt_body.get("messages", [])
            max_tokens = prompt_body.get("max_tokens", 4096)
            temperature = prompt_body.get("temperature", 0.1)
            top_p = prompt_body.get("top_p")
            response_format = prompt_body.get("response_format", None)

            # Additional args like response_format
            kwargs = {}
            if response_format:
                kwargs["response_format"] = response_format

            try:
                response = await acompletion(
                    model=settings.MODEL_ID,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    custom_llm_provider=settings.LLM_PROVIDER,
                    timeout=settings.LLM_TIMEOUT,
                    **kwargs,
                )
            except asyncio.TimeoutError:
                logger.error(f"LLM call timed out after {settings.LLM_TIMEOUT}s")
                raise RuntimeError("LLM processing timed out")

            usage = response.usage
            if usage:
                _llm_tokens_total[0] += getattr(
                    usage, "prompt_tokens", getattr(usage, "input_tokens", 0)
                )
                _llm_tokens_total[0] += getattr(
                    usage, "completion_tokens", getattr(usage, "output_tokens", 0)
                )

            llm_output = _parse_gateway_response(response)
            if (custom_output_format or response_format) and "result" in llm_output:
                logger.warning("Model response was not valid JSON; returning raw content")

            logger.info(f"LLM processing completed for {extraction_response.document_id}")
            return llm_output

        except Exception as e:
            logger.error(f"LLM enhancement failed: {str(e)}")
            raise

    async def process_pages_batch(
        self,
        pages_data: list[dict[str, Any]],
        custom_prompt: str = None,
        custom_output_format: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Process multiple pages with LLM concurrently"""
        tasks = [
            self._process_single_page(page_data, custom_prompt, custom_output_format)
            for page_data in pages_data
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Page {idx + 1} LLM processing failed: {str(result)}")
            else:
                successful_results.append(result)
        return successful_results

    async def _process_single_page(
        self,
        page_data: dict[str, Any],
        custom_prompt: str | None = None,
        custom_output_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a single page with LLM"""
        text = page_data.get("text_content", "")
        forms = page_data.get("forms", [])
        tables = page_data.get("tables", [])

        if custom_prompt:
            prompt_body = {
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": custom_prompt}],
                "temperature": 0.1,
            }
        else:
            builder = get_prompt_builder(None)
            prompt_body = builder(
                text=text,
                forms=forms,
                tables=tables,
                file_name=f"Page {page_data.get('page_number', 1)}",
                file_type="",
                pages_processed=1,
                total_pages=1,
                custom_output_format=custom_output_format,
            )

        messages = prompt_body.get("messages", [])
        max_tokens = prompt_body.get("max_tokens", 4096)
        temperature = prompt_body.get("temperature", 0.1)
        top_p = prompt_body.get("top_p")
        response_format = prompt_body.get("response_format", None)

        kwargs = {}
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await acompletion(
                model=settings.MODEL_ID,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                custom_llm_provider=settings.LLM_PROVIDER,
                timeout=settings.LLM_TIMEOUT,
                **kwargs,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("LLM call timed out")

        usage = response.usage
        if usage:
            _llm_tokens_total[0] += getattr(
                usage, "prompt_tokens", getattr(usage, "input_tokens", 0)
            )
            _llm_tokens_total[0] += getattr(
                usage, "completion_tokens", getattr(usage, "output_tokens", 0)
            )

        return _parse_gateway_response(response)

    def _build_prompt_request(
        self,
        extraction_response: ExtractionResponse,
        custom_prompt: str = None,
        custom_output_format: dict[str, Any] | None = None,
        prompt_version: str | None = None,
    ) -> dict[str, Any]:
        """Build prompt request body using prompt_builder with structured output support."""
        if custom_prompt:
            prompt_body = {
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": custom_prompt}],
                "temperature": 0.1,
            }
            if custom_output_format:
                try:
                    from app.core.prompts.idp.templates import convert_to_json_schema

                    json_schema = convert_to_json_schema(custom_output_format)
                    prompt_body["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "schema": json_schema,
                            "strict": True,
                            "name": "extraction_output",
                            "description": "Structured document extraction output matching the exact format specified",
                        },
                    }
                    logger.info("Attempting structured output with custom format")
                except Exception as e:
                    logger.warning(
                        f"Failed to create JSON schema for structured output: {str(e)}, using prompt instructions instead"
                    )
                enhanced_prompt = f"{custom_prompt}\n\nIMPORTANT: You must return your response as a valid JSON object that matches this EXACT structure:\n{json.dumps(custom_output_format, indent=2)}\n\nReturn ONLY the JSON object, no markdown, no explanations."
                prompt_body["messages"][0]["content"] = enhanced_prompt
            return prompt_body

        all_text = []
        all_forms = []
        all_tables = []
        for page in extraction_response.pages_data:
            if page.text_content:
                all_text.append(f"=== Page {page.page_number} ===\n{page.text_content}")
            for form in page.forms:
                all_forms.append({"key": form.key, "value": form.value, "page": page.page_number})
            for table in page.tables:
                all_tables.append(
                    {
                        "page": page.page_number,
                        "table_id": table.table_id,
                        "headers": table.headers,
                        "rows": table.rows[:5],
                    }
                )
        full_text = "\n\n".join(all_text)
        builder = get_prompt_builder(prompt_version)
        return builder(
            text=full_text,
            forms=all_forms,
            tables=all_tables,
            file_name=extraction_response.file_name,
            file_type=extraction_response.file_type,
            pages_processed=extraction_response.pages_processed,
            total_pages=extraction_response.total_pages,
            custom_output_format=custom_output_format,
        )
