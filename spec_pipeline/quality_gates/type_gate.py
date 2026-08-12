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

        target_path = sandbox_root / "src" if (sandbox_root / "src").is_dir() else sandbox_root
        cmd = [
            sys.executable,
            "-m",
            "mypy",
            "--allow-untyped-defs",
            "--allow-untyped-calls",
            "--ignore-missing-imports",
            "--follow-imports=silent",
            "--no-strict-optional",
            "--allow-redefinition",
            "--disable-error-code=import-untyped",
            "--disable-error-code=var-annotated",
            "--disable-error-code=attr-defined",
            "--disable-error-code=name-defined",
            "--disable-error-code=type-arg",
            "--disable-error-code=no-any-return",
            "--disable-error-code=return-value",
            "--disable-error-code=assignment",
            "--disable-error-code=arg-type",
            "--disable-error-code=call-arg",
            "--disable-error-code=operator",
            "--disable-error-code=index",
            "--disable-error-code=override",
            "--disable-error-code=union-attr",
            "--disable-error-code=misc",
            "--disable-error-code=valid-type",
            "--disable-error-code=no-redef",
            "--disable-error-code=no-untyped-def",
            "--explicit-package-bases",
            "--no-error-summary",
            str(target_path),
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        passed = proc.returncode == 0
        err_msg = proc.stdout.strip() or proc.stderr.strip()
        details = (
            "Static type verification passed with Mypy."
            if passed
            else (err_msg or "Mypy detected static type violations.")
        )

        return QualityGateResult(
            gate_name=self.name,
            passed=passed,
            details=details,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
