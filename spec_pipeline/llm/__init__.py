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
    if config is None:
        cfg = LLMConfig(
            provider=provider_type or "mock",
            model=model_name or ("mock-model" if (provider_type or "mock") == "mock" else ""),
            api_key=api_key or "",
        )
    else:
        cfg = config

    provider = cfg.provider.lower()

    if provider == "gemini":
        from spec_pipeline.llm.gemini_provider import GeminiProvider

        return GeminiProvider(cfg)

    if provider == "openai":
        from spec_pipeline.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(cfg)

    if provider == "mock":
        from spec_pipeline.llm.mock_provider import MockProvider

        return MockProvider(cfg)

    raise ValueError(
        f"Unknown LLM provider: {cfg.provider!r}. "
        "Supported: 'gemini', 'openai', 'mock'."
    )
