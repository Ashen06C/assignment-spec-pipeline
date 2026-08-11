"""Gate 3: Static type safety verification using Mypy."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class TypeGate(BaseQualityGate):
    """Executes Mypy static type checking on the sandbox directory."""

    name = "typecheck"

    def _run(
        self,
        sandbox_root: Path,
        spec: FeatureSpec | None = None,
        plan: ImplementationPlan | None = None,
        tests: list[SynthesizedTest] | None = None,
    ) -> QualityGateResult:
        py_files = list(sandbox_root.rglob("*.py"))
        if not py_files:
            return QualityGateResult(
                gate_name=self.name,
                passed=True,
                details="No Python files to typecheck.",
            )

        cmd = [
            sys.executable,
            "-m",
            "mypy",
            "--allow-untyped-defs",
            "--ignore-missing-imports",
            "--explicit-package-bases",
            "--no-error-summary",
            str(sandbox_root),
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        passed = proc.returncode == 0
        details = (
            "Static type verification passed with Mypy."
            if passed
            else "Mypy detected static type violations."
        )

        return QualityGateResult(
            gate_name=self.name,
            passed=passed,
            details=details,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
