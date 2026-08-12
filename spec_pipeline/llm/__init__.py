"""LLM abstraction layer — provider factory and re-exports.

Usage::

    from spec_pipeline.llm import get_llm_provider, LLMConfig

    config = LLMConfig(provider="mock")
    llm = get_llm_provider(config)
    text, usage = llm.generate("Summarise this feature spec …")
"""

from __future__ import annotations

from spec_pipeline.llm.base import BaseLLMProvider, LLMConfig, TokenUsage
from spec_pipeline.llm.mock_provider import MockProvider

__all__ = [
    "BaseLLMProvider",
    "LLMConfig",
    "MockProvider",
    "TokenUsage",
    "get_llm_provider",
]


def get_llm_provider(
    config: LLMConfig | None = None,
    provider_type: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> BaseLLMProvider:
    """Instantiate the correct LLM provider from *config* or keyword arguments."""
    from spec_pipeline.core.config import load_settings

    settings = load_settings()

    p_type = (
        provider_type
        or (config.provider if config else None)
        or settings.llm_provider
        or "mock"
    ).lower()

    # Resolve API key
    resolved_key = api_key or (config.api_key if config else "")
    if not resolved_key:
        if p_type == "openai":
            resolved_key = settings.openai_api_key
        elif p_type == "gemini":
            resolved_key = settings.gemini_api_key

    # Resolve model
    resolved_model = model_name or (config.model if config else "")
    if not resolved_model:
        if p_type == "openai":
            resolved_model = "gpt-4o"
        elif p_type == "gemini":
            resolved_model = "gemini-2.5-flash"
        elif p_type == "mock":
            resolved_model = "mock-model"

    cfg = LLMConfig(
        provider=p_type,
        model=resolved_model,
        api_key=resolved_key,
    )

    if p_type == "gemini":
        from spec_pipeline.llm.gemini_provider import GeminiProvider

        return GeminiProvider(cfg)

    if p_type == "openai":
        from spec_pipeline.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(cfg)

    if p_type == "mock":
        from spec_pipeline.llm.mock_provider import MockProvider

        return MockProvider(cfg)

    raise ValueError(
        f"Unknown LLM provider: {p_type!r}. "
        "Supported providers: 'mock', 'gemini', 'openai'."
    )
