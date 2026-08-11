"""Gate 1: Python AST syntax verification."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest


class SyntaxGate(BaseQualityGate):
    """Parses all Python files under sandbox_root into ASTs to detect syntax errors."""

    name = "syntax"

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
                details="No Python files to verify.",
            )

        errors: list[str] = []
        for file_path in py_files:
            try:
                source = file_path.read_text(encoding="utf-8")
                ast.parse(source, filename=str(file_path))
            except SyntaxError as err:
                rel_path = file_path.relative_to(sandbox_root)
                errors.append(f"{rel_path}:{err.lineno}:{err.offset}: {err.msg}")

        if errors:
            return QualityGateResult(
                gate_name=self.name,
                passed=False,
                details=f"Syntax errors detected in {len(errors)} location(s).",
                stderr="\n".join(errors),
            )

        return QualityGateResult(
            gate_name=self.name,
            passed=True,
            details=f"All {len(py_files)} Python files parsed successfully with valid AST syntax.",
        )
