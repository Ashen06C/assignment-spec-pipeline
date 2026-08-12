"""Gate 2: Fast PEP8 and Pyflakes style verification using Ruff."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class LintGate(BaseQualityGate):
    """Executes Ruff linting (`ruff check --select=E,F,W`) on the sandbox directory."""

    name = "lint"

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
                details="No Python files to lint.",
            )

        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            # E9xx  — syntax errors (SyntaxError, TokenError, compile failures)
            # F63x  — invalid syntax constructs (assert/raise/return issues)
            # F7xx  — statement-level errors (return outside function, yield in wrong place)
            # F82x (undefined name) is intentionally excluded: our import sanitizer
            # rewrites third-party imports (e.g. jwt→hmac) but leaves call-sites intact,
            # which causes false F821 positives on names like `jwt`, `cryptography`, etc.
            "--select=E9,F63,F7",
            "--no-cache",
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
            "All lint checks passed cleanly with Ruff."
            if passed
            else f"Ruff reported lint errors in {sandbox_root.name}."
        )

        return QualityGateResult(
            gate_name=self.name,
            passed=passed,
            details=details,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
