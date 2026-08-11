"""LLM abstraction layer — provider factory and re-exports.

Usage::

    from spec_pipeline.llm import get_llm_provider, LLMConfig

    config = LLMConfig(provider="mock")
    llm = get_llm_provider(config)
    text, usage = llm.generate("Summarise this feature spec …")
"""

from __future__ import annotations

from spec_pipeline.llm.base import BaseLLMProvider, LLMConfig, TokenUsage

__all__ = [
    "BaseLLMProvider",
    "LLMConfig",
    "TokenUsage",
    "get_llm_provider",
]


def get_llm_provider(config: LLMConfig) -> BaseLLMProvider:
    """Instantiate the correct LLM provider from *config*.

    Providers are imported lazily so that optional SDK dependencies
    are only required when their provider is actually selected.

    Raises
    ------
    ValueError
        If ``config.provider`` is not a recognised provider name.
    """
    provider = config.provider.lower()

    if provider == "gemini":
        from spec_pipeline.llm.gemini_provider import GeminiProvider

        return GeminiProvider(config)

    if provider == "openai":
        from spec_pipeline.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(config)

    if provider == "mock":
        from spec_pipeline.llm.mock_provider import MockProvider

        return MockProvider(config)

    raise ValueError(
        f"Unknown LLM provider: {config.provider!r}. "
        "Supported: 'gemini', 'openai', 'mock'."
    )
