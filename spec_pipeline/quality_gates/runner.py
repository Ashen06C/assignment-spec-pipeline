"""Quality Gate Runner coordinating all deterministic verification checkpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from spec_pipeline.core.exceptions import QualityGateFailureError
from spec_pipeline.core.models import QualityGateSuiteResult
from spec_pipeline.quality_gates.ac_gate import AcceptanceCriteriaGate
from spec_pipeline.quality_gates.lint_gate import LintGate
from spec_pipeline.quality_gates.security_gate import SecurityGate
from spec_pipeline.quality_gates.syntax_gate import SyntaxGate
from spec_pipeline.quality_gates.test_gate import TestGate
from spec_pipeline.quality_gates.type_gate import TypeGate

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from spec_pipeline.core.models import (
        FeatureSpec,
        ImplementationPlan,
        QualityGateResult,
        SynthesizedTest,
    )
    from spec_pipeline.quality_gates.base import BaseQualityGate


class QualityGateRunner:
    """Coordinates the deterministic execution of the 6 quality gates."""

    def __init__(self, gates: Sequence[BaseQualityGate] | None = None) -> None:
        if gates is None:
            self.gates: list[BaseQualityGate] = [
                SyntaxGate(),
                LintGate(),
                TypeGate(),
                SecurityGate(),
                TestGate(),
                AcceptanceCriteriaGate(),
            ]
        else:
            self.gates = list(gates)

    def execute_all_gates(
        self,
        sandbox_root: Path,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        tests: list[SynthesizedTest] | None = None,
        raise_on_failure: bool = False,
    ) -> QualityGateSuiteResult:
        """Run all configured quality gates sequentially and aggregate results."""
        results: list[QualityGateResult] = []

        for gate in self.gates:
            gate_result = gate.execute(
                sandbox_root=sandbox_root,
                spec=spec,
                plan=plan,
                tests=tests,
            )
            results.append(gate_result)

        all_passed = all(r.passed for r in results)

        suite_result = QualityGateSuiteResult(
            plan_id=plan.plan_id,
            gates=results,
            all_passed=all_passed,
        )

        if raise_on_failure and not all_passed:
            failed_names = [r.gate_name for r in results if not r.passed]
            raise QualityGateFailureError(failed_gates=failed_names)

        return suite_result
