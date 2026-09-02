"""IDP integration-test env (mirrors unit/idp so app import sees defaults)."""

import os

if "EXTRACTOR_TYPE" not in os.environ:
    os.environ["EXTRACTOR_TYPE"] = "goml_custom_extractor"
if "AUTH_METHOD" not in os.environ:
    os.environ["AUTH_METHOD"] = "none"
if "BUCKET_NAME" not in os.environ:
    os.environ["BUCKET_NAME"] = ""
if "LLM_PROVIDER" not in os.environ:
    os.environ["LLM_PROVIDER"] = "openai"
if "OPENAI_API_KEY" not in os.environ:
    os.environ["OPENAI_API_KEY"] = "sk-test-key"
if "MODEL_ID" not in os.environ:
    os.environ["MODEL_ID"] = ""
