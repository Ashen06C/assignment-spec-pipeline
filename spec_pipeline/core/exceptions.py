"""Domain-specific exceptions for the spec-driven pipeline."""

from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline errors."""


class SpecValidationError(PipelineError):
    """Raised when a feature specification fails structural validation.

    Attributes
    ----------
    missing_sections : list[str]
        Names of the required sections that are absent.
    """

    def __init__(self, missing_sections: list[str], message: str | None = None) -> None:
        self.missing_sections = missing_sections
        super().__init__(
            message
            or f"Specification is missing required sections: {', '.join(missing_sections)}"
        )


class SandboxPolicyViolationError(PipelineError):
    """Raised when generated code attempts to modify disallowed paths."""

    def __init__(self, violating_paths: list[str]) -> None:
        self.violating_paths = violating_paths
        super().__init__(
            f"Sandbox policy violation — changes to disallowed paths: "
            f"{', '.join(violating_paths)}"
        )


class QualityGateFailureError(PipelineError):
    """Raised when one or more quality gates fail."""

    def __init__(self, failed_gates: list[str]) -> None:
        self.failed_gates = failed_gates
        super().__init__(
            f"Quality gate(s) failed: {', '.join(failed_gates)}"
        )


class ApprovalRejectedError(PipelineError):
    """Raised when a human reviewer rejects a pipeline checkpoint."""

    def __init__(self, checkpoint: str, reason: str = "") -> None:
        self.checkpoint = checkpoint
        self.reason = reason
        super().__init__(
            f"Approval rejected at checkpoint '{checkpoint}'"
            + (f": {reason}" if reason else "")
        )


class LLMProviderError(PipelineError):
    """Raised when communication with the LLM provider fails."""

    def __init__(self, provider: str, detail: str = "") -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(
            f"LLM provider error ({provider})"
            + (f": {detail}" if detail else "")
        )
