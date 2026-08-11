"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _find_dotenv() -> Path | None:
    """Walk upward from CWD to locate a .env file."""
    current = Path.cwd()
    for directory in (current, *current.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    """Immutable snapshot of pipeline-wide settings."""

    gemini_api_key: str
    openai_api_key: str
    llm_provider: str   # "gemini" | "openai"
    llm_model: str

    # ---- derived helpers -------------------------------------------------- #

    @property
    def active_api_key(self) -> str:
        """Return the API key that matches the selected provider."""
        if self.llm_provider == "gemini":
            return self.gemini_api_key
        if self.llm_provider == "openai":
            return self.openai_api_key
        raise ValueError(f"Unsupported LLM provider: {self.llm_provider!r}")


def load_settings(dotenv_path: Path | None = None) -> PipelineSettings:
    """Load pipeline settings from environment variables.

    Parameters
    ----------
    dotenv_path:
        Explicit path to a ``.env`` file.  When *None* the function searches
        upward from the current working directory.

    Returns
    -------
    PipelineSettings
        Frozen dataclass with validated configuration values.
    """
    env_path = dotenv_path or _find_dotenv()
    if env_path is not None:
        load_dotenv(env_path, override=False)

    return PipelineSettings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "gemini").lower(),
        llm_model=os.getenv("LLM_MODEL", "gemini-2.5-flash"),
    )
