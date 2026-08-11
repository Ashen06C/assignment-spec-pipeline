"""Abstract base class and shared types for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token consumption metrics from a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Provider-agnostic configuration for an LLM call."""

    provider: str = "mock"              # gemini | openai | mock
    model: str = "gemini-2.5-flash"
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 8192
    extra: dict[str, object] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Contract that every LLM provider must fulfil.

    Subclasses implement :meth:`generate` to call a specific model API
    and return ``(response_text, token_usage)``.
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> tuple[str, TokenUsage]:
        """Send *prompt* to the model and return ``(text, usage)``.

        Parameters
        ----------
        prompt:
            The user/task prompt.
        system_prompt:
            Optional system-level instruction.
        temperature:
            Override the default temperature for this call.

        Returns
        -------
        tuple[str, TokenUsage]
            The model's text response and token-usage metrics.
        """
        ...
