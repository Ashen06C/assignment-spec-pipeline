"""OpenAI LLM provider — native REST client."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from spec_pipeline.core.exceptions import LLMProviderError
from spec_pipeline.llm.base import BaseLLMProvider, LLMConfig, TokenUsage

_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(BaseLLMProvider):
    """Calls the OpenAI Chat Completions REST API."""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        if not config.api_key:
            raise LLMProviderError("openai", "OPENAI_API_KEY is not set")

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> tuple[str, TokenUsage]:
        temp = temperature if temperature is not None else self.config.temperature
        model = self.config.model or "gpt-4o"

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": self.config.max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        try:
            req = urllib.request.Request(
                _OPENAI_API_URL,
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())
        except Exception as exc:
            raise LLMProviderError("openai", str(exc)) from exc

        # Extract text.
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMProviderError(
                "openai", f"Unexpected response structure: {data}"
            ) from exc

        # Extract usage.
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return text, usage
