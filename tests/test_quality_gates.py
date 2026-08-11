"""Tests for the 6 deterministic quality gates and the QualityGateRunner."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from spec_pipeline.core.exceptions import QualityGateFailureError
from spec_pipeline.core.models import (
    AcceptanceCriterion,
    BusinessRule,
    DecomposedTask,
    FeatureSpec,
    ImplementationPlan,
    NonFunctionalRequirement,
    SynthesizedTest,
    UserStory,
)
from spec_pipeline.quality_gates.ac_gate import AcceptanceCriteriaGate
from spec_pipeline.quality_gates.lint_gate import LintGate
from spec_pipeline.quality_gates.runner import QualityGateRunner
from spec_pipeline.quality_gates.security_gate import SecurityGate
from spec_pipeline.quality_gates.syntax_gate import SyntaxGate
from spec_pipeline.quality_gates.test_gate import TestGate
from spec_pipeline.quality_gates.type_gate import TypeGate


def _create_sample_spec() -> FeatureSpec:
    """Create sample valid spec."""
    return FeatureSpec(
        title="Calculator Service",
        objective="Perform arithmetic",
        user_stories=[UserStory(as_a="user", i_want="to add", so_that="I get sum")],
        business_rules=[BusinessRule(rule_id="BR-001", description="Numbers must be integers")],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="Addition",
                given="2 and 3",
                when="added",
                then="returns 5",
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="performance", description="Instant")
        ],
        out_of_scope=["Division by zero handling in v1"],
    )


def _create_sample_plan() -> ImplementationPlan:
    """Create sample valid plan."""
    return ImplementationPlan(
        spec_id=uuid4(),
        technical_summary="Calculator plan",
        impacted_files=["src/calc.py"],
        tasks=[
            DecomposedTask(
                task_id="TASK-001",
                title="Add calc",
                description="desc",
                target_files=["src/calc.py"],
            )
        ],
    )


def _setup_sandbox(sandbox_dir: Path, code: str, test_code: str) -> None:
    """Populate sandbox with src and tests."""
    src_dir = sandbox_dir / "src"
    tests_dir = sandbox_dir / "tests"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    (src_dir / "__init__.py").write_text("", encoding="utf-8")
    (src_dir / "calc.py").write_text(code, encoding="utf-8")

    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))\n",
        encoding="utf-8",
    )
    (tests_dir / "test_calc.py").write_text(test_code, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Individual Gate Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSyntaxGate:
    def test_passes_valid_syntax(self, tmp_path: Path) -> None:
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        _setup_sandbox(tmp_path, code, "def test_add(): pass\n")
        gate = SyntaxGate()
        res = gate.execute(tmp_path)
        assert res.passed is True
        assert res.duration_seconds is not None

    def test_fails_invalid_syntax(self, tmp_path: Path) -> None:
        _setup_sandbox(tmp_path, "def broken_syntax(\n", "def test_x(): pass\n")
        gate = SyntaxGate()
        res = gate.execute(tmp_path)
        assert res.passed is False
        assert "Syntax errors detected" in res.details


class TestLintGate:
    def test_passes_clean_code(self, tmp_path: Path) -> None:
        clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        _setup_sandbox(tmp_path, clean_code, "def test_add() -> None:\n    pass\n")
        gate = LintGate()
        res = gate.execute(tmp_path)
        assert res.passed is True

    def test_fails_undefined_variable(self, tmp_path: Path) -> None:
        bad_code = "def add():\n    return undefined_var_xyz\n"
        _setup_sandbox(tmp_path, bad_code, "def test_add(): pass\n")
        gate = LintGate()
        res = gate.execute(tmp_path)
        assert res.passed is False
        assert "F821" in res.stdout or "undefined_var_xyz" in res.stdout


class TestTypeGate:
    def test_passes_typed_code(self, tmp_path: Path) -> None:
        clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        _setup_sandbox(tmp_path, clean_code, "def test_add() -> None:\n    pass\n")
        gate = TypeGate()
        res = gate.execute(tmp_path)
        assert res.passed is True


class TestSecurityGate:
    def test_passes_safe_code(self, tmp_path: Path) -> None:
        clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        _setup_sandbox(tmp_path, clean_code, "def test_add(): pass\n")
        gate = SecurityGate()
        res = gate.execute(tmp_path)
        assert res.passed is True

    def test_detects_eval_and_exec(self, tmp_path: Path) -> None:
        unsafe_code = "def run(x):\n    eval(x)\n    exec('import os')\n"
        _setup_sandbox(tmp_path, unsafe_code, "def test_run(): pass\n")
        gate = SecurityGate()
        res = gate.execute(tmp_path)
        assert res.passed is False
        assert "Dangerous primitive 'eval()'" in res.stderr
        assert "Dangerous primitive 'exec()'" in res.stderr

    def test_detects_hardcoded_secrets(self, tmp_path: Path) -> None:
        leaked_key_code = 'api_key = "sk-123456789012345678901234567890"\n'
        _setup_sandbox(tmp_path, leaked_key_code, "def test_x(): pass\n")
        gate = SecurityGate()
        res = gate.execute(tmp_path)
        assert res.passed is False
        assert "secret" in res.stderr.lower() or "key" in res.stderr.lower()


class TestTestGate:
    def test_passes_successful_tests(self, tmp_path: Path) -> None:
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        test_code = "from calc import add\ndef test_add():\n    assert add(2, 3) == 5\n"
        _setup_sandbox(tmp_path, code, test_code)
        gate = TestGate()
        res = gate.execute(tmp_path)
        assert res.passed is True

    def test_fails_broken_tests(self, tmp_path: Path) -> None:
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        test_code = "from calc import add\ndef test_add():\n    assert add(2, 3) == 999\n"
        _setup_sandbox(tmp_path, code, test_code)
        gate = TestGate()
        res = gate.execute(tmp_path)
        assert res.passed is False
        assert "failed" in res.details.lower()


class TestAcceptanceCriteriaGate:
    def test_passes_when_all_criteria_covered(self, tmp_path: Path) -> None:
        spec = _create_sample_spec()
        tests = [
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="AC-001 verification",
                source_criterion_id="AC-001",
                file_path="tests/test_calc.py",
                source_code="def test_addition(): assert True\n",
            )
        ]
        gate = AcceptanceCriteriaGate()
        res = gate.execute(tmp_path, spec=spec, tests=tests)
        assert res.passed is True
        assert "100%" in res.details

    def test_fails_when_criterion_is_unmapped(self, tmp_path: Path) -> None:
        spec = _create_sample_spec()
        tests: list[SynthesizedTest] = []  # No tests mapped
        gate = AcceptanceCriteriaGate()
        res = gate.execute(tmp_path, spec=spec, tests=tests)
        assert res.passed is False
        assert "Unmapped criteria: AC-001" in res.details


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Quality Gate Runner Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestQualityGateRunner:
    def test_execute_all_gates_clean(self, tmp_path: Path) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()
        code = "def add(a: int, b: int) -> int:\n    return a + b\n"
        test_code = "from calc import add\ndef test_addition():\n    assert add(2, 3) == 5\n"
        _setup_sandbox(tmp_path, code, test_code)

        tests = [
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="AC-001 verification",
                source_criterion_id="AC-001",
                file_path="tests/test_calc.py",
                source_code=test_code,
            )
        ]

        runner = QualityGateRunner()
        suite = runner.execute_all_gates(
            sandbox_root=tmp_path,
            spec=spec,
            plan=plan,
            tests=tests,
            raise_on_failure=False,
        )

        assert suite.all_passed is True
        assert len(suite.gates) == 6
        for gate_res in suite.gates:
            assert gate_res.passed is True
            assert gate_res.duration_seconds is not None

    def test_execute_all_gates_raises_on_failure(self, tmp_path: Path) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()
        # Syntax error in sandbox code
        _setup_sandbox(tmp_path, "def broken(\n", "def test_x(): pass\n")

        runner = QualityGateRunner()
        with pytest.raises(QualityGateFailureError) as exc_info:
            runner.execute_all_gates(
                sandbox_root=tmp_path,
                spec=spec,
                plan=plan,
                tests=[],
                raise_on_failure=True,
            )

        assert "syntax" in str(exc_info.value)
