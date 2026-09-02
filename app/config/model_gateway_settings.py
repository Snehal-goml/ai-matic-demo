"""Configuration owned by the shared model gateway."""

from pydantic_settings import BaseSettings


class ModelGatewaySettings(BaseSettings):
    LLM_PROVIDER: str = "bedrock"
    MODEL_ID: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_API_BASE: str = ""
    EMBEDDING_MODEL_ID: str = ""
    NOVA_SONIC_MODEL_ID: str = ""
    LLM_TIMEOUT: int = 60
