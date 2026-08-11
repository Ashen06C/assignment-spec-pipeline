"""Gate 5: Automated test execution using Pytest in the sandbox environment."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class TestGate(BaseQualityGate):
    """Executes generated Pytest test suites within the sandbox environment."""

    __test__ = False

    name = "pytest"

    def _run(
        self,
        sandbox_root: Path,
        spec: FeatureSpec | None = None,
        plan: ImplementationPlan | None = None,
        tests: list[SynthesizedTest] | None = None,
    ) -> QualityGateResult:
        tests_dir = sandbox_root / "tests"
        if not tests_dir.is_dir() or not list(tests_dir.glob("test_*.py")):
            return QualityGateResult(
                gate_name=self.name,
                passed=True,
                details="No test suites found in sandbox tests directory.",
            )

        src_dir = sandbox_root / "src"

        # Build clean environment with sandbox src and root on PYTHONPATH
        env = dict(os.environ)
        pythonpath = os.pathsep.join(
            [str(src_dir), str(sandbox_root), env.get("PYTHONPATH", "")]
        )
        env["PYTHONPATH"] = pythonpath

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(tests_dir),
            "-v",
            "--no-header",
            "--tb=short",
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        passed = proc.returncode == 0
        details = (
            "All test suites executed and passed successfully."
            if passed
            else "One or more automated test suites failed."
        )

        return QualityGateResult(
            gate_name=self.name,
            passed=passed,
            details=details,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
