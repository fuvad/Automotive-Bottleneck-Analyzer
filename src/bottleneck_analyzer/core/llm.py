"""Bounded structured-output adapter. No SQL, Python execution, or model tools."""

import json
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel

from bottleneck_analyzer.core.config import AppSettings


class LLMUnavailable(ValueError):
    """Public errors deliberately exclude provider responses and credentials."""


class StructuredLLM(Protocol):
    def generate[T: BaseModel](self, instruction: str, data: dict, schema: type[T]) -> T: ...


def strict_schema(schema: dict) -> dict:
    """Require nullable optional fields explicitly, per the structured-output API."""
    result = {k: v for k, v in schema.items() if k != "default"}
    if "const" in result:
        result["enum"] = [result.pop("const")]
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return {
        k: strict_schema(v)
        if isinstance(v, dict)
        else [strict_schema(i) if isinstance(i, dict) else i for i in v]
        if isinstance(v, list)
        else v
        for k, v in result.items()
    }


class OpenAIStructuredLLM:
    """Reuse the embedding adapter's stdlib HTTPS convention; zero automatic retries."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def generate[T: BaseModel](self, instruction: str, data: dict, schema: type[T]) -> T:
        settings = self.settings
        if settings.llm_provider != "openai" or not settings.llm_model:
            raise LLMUnavailable("LLM provider/model is not configured or supported")
        if not settings.llm_api_key or not settings.llm_api_key.get_secret_value():
            raise LLMUnavailable("LLM API key is not configured")
        url = urlparse(settings.llm_base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise LLMUnavailable("LLM endpoint must be an HTTPS base URL")
        user_data = json.dumps(data, ensure_ascii=True)
        if len(user_data) > 60000:
            raise LLMUnavailable("LLM context exceeds the bounded input limit")
        body = {
            "model": settings.llm_model,
            "store": False,
            "instructions": instruction,
            "input": user_data,
            "max_output_tokens": settings.llm_max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema.__name__,
                    "strict": True,
                    "schema": strict_schema(schema.model_json_schema()),
                }
            },
        }
        request = Request(
            settings.llm_base_url.rstrip("/") + "/responses",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + settings.llm_api_key.get_secret_value(),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
                payload = json.loads(response.read(1_000_001))
            if payload.get("status") != "completed":
                raise LLMUnavailable("LLM response was incomplete")
            parts = [
                content["text"]
                for output in payload["output"]
                if output["type"] == "message"
                for content in output["content"]
                if content["type"] == "output_text"
            ]
            if len(parts) != 1:
                raise LLMUnavailable("LLM refused or returned no single structured result")
            return schema.model_validate_json(parts[0])
        except (URLError, OSError, TimeoutError, KeyError, TypeError, ValueError):
            raise LLMUnavailable(
                "LLM provider failed or returned invalid structured output"
            ) from None
