"""Gate 6: 100% Acceptance Criteria Traceability & Coverage Gate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate
from spec_pipeline.testing.traceability import TraceabilityMatrixBuilder

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class AcceptanceCriteriaGate(BaseQualityGate):
    """Verifies that 100% of specification Acceptance Criteria are mapped to executable tests."""

    name = "acceptance_criteria"

    def __init__(self, matrix_builder: TraceabilityMatrixBuilder | None = None) -> None:
        self.matrix_builder = matrix_builder or TraceabilityMatrixBuilder()

    def _run(
        self,
        sandbox_root: Path,
        spec: FeatureSpec | None = None,
        plan: ImplementationPlan | None = None,
        tests: list[SynthesizedTest] | None = None,
    ) -> QualityGateResult:
        if spec is None:
            return QualityGateResult(
                gate_name=self.name,
                passed=True,
                details="No feature specification provided for AC verification.",
            )

        test_list = tests or []
        matrix = self.matrix_builder.build(spec, test_list)

        if matrix.uncovered_criteria:
            uncovered_str = ", ".join(matrix.uncovered_criteria)
            pct = int(matrix.coverage_ratio * 100)
            return QualityGateResult(
                gate_name=self.name,
                passed=False,
                details=(
                    f"Acceptance criteria coverage is {pct}% (< 100%). "
                    f"Unmapped criteria: {uncovered_str}"
                ),
                stdout=matrix.render_matrix_markdown(),
            )

        pct = int(matrix.coverage_ratio * 100)
        total = len(matrix.entries)
        return QualityGateResult(
            gate_name=self.name,
            passed=True,
            details=f"100% AC coverage verified ({total}/{total} mapped).",
            stdout=matrix.render_matrix_markdown(),
        )
