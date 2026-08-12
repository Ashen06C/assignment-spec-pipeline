"""Google Gemini LLM provider — native REST client."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from spec_pipeline.core.exceptions import LLMProviderError
from spec_pipeline.llm.base import BaseLLMProvider, LLMConfig, TokenUsage

_GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(BaseLLMProvider):
    """Calls the Google Gemini REST API (``generativelanguage.googleapis.com``)."""

    def __init__(self, config: LLMConfig) -> None:
        key = config.api_key
        if not key:
            from spec_pipeline.core.config import load_settings

            key = load_settings().gemini_api_key

        if not key:
            raise LLMProviderError("gemini", "GEMINI_API_KEY is not set in environment or .env")

        if key != config.api_key:
            config = LLMConfig(
                provider=config.provider,
                model=config.model,
                api_key=key,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                extra=config.extra,
            )
        super().__init__(config)

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> tuple[str, TokenUsage]:
        temp = temperature if temperature is not None else self.config.temperature
        model = self.config.model or "gemini-2.5-flash"

        # Build request body.
        contents: list[dict[str, Any]] = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": system_prompt}],
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}],
            })
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temp,
                "maxOutputTokens": self.config.max_tokens,
            },
        }

        url = _GEMINI_API_URL.format(model=model) + f"?key={self.config.api_key}"
        headers = {"Content-Type": "application/json"}

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())
        except Exception as exc:
            raise LLMProviderError("gemini", str(exc)) from exc

        # Extract text.
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMProviderError(
                "gemini", f"Unexpected response structure: {data}"
            ) from exc

        # Extract usage.
        usage_data = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("promptTokenCount", 0),
            completion_tokens=usage_data.get("candidatesTokenCount", 0),
            total_tokens=usage_data.get("totalTokenCount", 0),
        )

        return text, usage
