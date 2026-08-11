"""Gate 4: AST Security Scanner detecting dangerous primitives and hardcoded secrets."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from spec_pipeline.core.models import QualityGateResult
from spec_pipeline.quality_gates.base import BaseQualityGate

if TYPE_CHECKING:
    from pathlib import Path

    from spec_pipeline.core.models import FeatureSpec, ImplementationPlan, SynthesizedTest

DANGEROUS_FUNCTIONS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "__import__",
        "compile",
    }
)

SECRET_PATTERNS = [
    (r"\b(sk-[a-zA-Z0-9]{20,})\b", "OpenAI secret API key pattern"),
    (r"\b(ghp_[a-zA-Z0-9]{20,})\b", "GitHub personal access token pattern"),
    (r"\b(AIza[0-9A-Za-z-_]{35})\b", "Google API key pattern"),
    (
        r"""(?i)\b(api_key|secret|password|auth_token)\s*=\s*['"][a-zA-Z0-9_\-]{8,}['"]""",
        "Hardcoded secret assignment",
    ),
]


class SecurityASTVisitor(ast.NodeVisitor):
    """Inspects AST nodes for dangerous primitives and unsafe function invocations."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct calls (e.g. eval(), exec())
        if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_FUNCTIONS:
            self.findings.append(
                f"{self.filename}:{node.lineno}: Dangerous primitive '{node.func.id}()' invocation"
            )

        # Check os.system()
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "system"
        ):
            self.findings.append(
                f"{self.filename}:{node.lineno}: Dangerous primitive 'os.system()' invocation"
            )

        self.generic_visit(node)


class SecurityGate(BaseQualityGate):
    """Detects dangerous code execution primitives and hardcoded secrets."""

    name = "security"

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
                details="No Python files to scan for security vulnerabilities.",
            )

        findings: list[str] = []

        for file_path in py_files:
            rel_path = str(file_path.relative_to(sandbox_root))
            content = file_path.read_text(encoding="utf-8")

            # 1. Regex Hardcoded Secret Scanner
            for pattern, desc in SECRET_PATTERNS:
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    if (
                        re.search(pattern, line)
                        and "your_" not in line.lower()
                        and "placeholder" not in line.lower()
                    ):
                        findings.append(f"{rel_path}:{line_idx}: {desc} detected")

            # 2. AST Primitive Scanner
            try:
                tree = ast.parse(content, filename=rel_path)
                visitor = SecurityASTVisitor(rel_path)
                visitor.visit(tree)
                findings.extend(visitor.findings)
            except SyntaxError:
                # Syntax errors are handled by SyntaxGate
                pass

        if findings:
            return QualityGateResult(
                gate_name=self.name,
                passed=False,
                details=f"Security gate detected {len(findings)} vulnerability finding(s).",
                stderr="\n".join(findings),
            )

        return QualityGateResult(
            gate_name=self.name,
            passed=True,
            details="Security scan passed with zero dangerous primitives or hardcoded secrets.",
        )
