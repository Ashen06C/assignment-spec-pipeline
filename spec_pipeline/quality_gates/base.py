"""Base quality gate contract and shared types."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class BaseQualityGate(ABC):
    """Abstract base class for all deterministic quality verification gates."""

    name: str

    def execute(
        self,
        sandbox_root: Path,
        spec: FeatureSpec | None = None,
        plan: ImplementationPlan | None = None,
        tests: list[SynthesizedTest] | None = None,
    ) -> QualityGateResult:
        """Run the gate check and measure its exact execution duration."""
        start_time = time.perf_counter()
        try:
            result = self._run(sandbox_root, spec, plan, tests)
        except Exception as exc:
            duration = time.perf_counter() - start_time
            return QualityGateResult(
                gate_name=self.name,
                passed=False,
                details=f"Gate encountered unexpected error: {exc}",
                stderr=str(exc),
                duration_seconds=round(duration, 4),
            )

        duration = time.perf_counter() - start_time
        return QualityGateResult(
            gate_name=self.name,
            passed=result.passed,
            details=result.details,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=round(duration, 4),
        )

    @abstractmethod
    def _run(
        self,
        sandbox_root: Path,
        spec: FeatureSpec | None = None,
        plan: ImplementationPlan | None = None,
        tests: list[SynthesizedTest] | None = None,
    ) -> QualityGateResult:
        """Execute the gate-specific check logic."""
        ...
