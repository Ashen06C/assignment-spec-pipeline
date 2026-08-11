"""Tests for the automated test generator and bidirectional traceability matrix."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from spec_pipeline.core.models import (
    AcceptanceCriterion,
    BusinessRule,
    DecomposedTask,
    FeatureSpec,
    FileChange,
    ImplementationOutput,
    ImplementationPlan,
    NonFunctionalRequirement,
    SynthesizedTest,
    UserStory,
)
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, MockProvider, TokenUsage
from spec_pipeline.testing.test_generator import TestGenerator
from spec_pipeline.testing.traceability import TraceabilityMatrixBuilder


@pytest.fixture
def matrix_builder() -> TraceabilityMatrixBuilder:
    return TraceabilityMatrixBuilder()


def _create_sample_spec() -> FeatureSpec:
    """Helper creating a spec with 3 acceptance criteria."""
    return FeatureSpec(
        title="Payment Service",
        objective="Process payments securely",
        user_stories=[UserStory(as_a="buyer", i_want="to pay", so_that="order completes")],
        business_rules=[BusinessRule(rule_id="BR-001", description="Valid amount required")],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="Credit card charge",
                given="valid card",
                when="charge requested",
                then="success returned",
            ),
            AcceptanceCriterion(
                criterion_id="AC-002",
                title="Insufficient funds",
                given="card with 0 balance",
                when="charge requested",
                then="decline returned",
            ),
            AcceptanceCriterion(
                criterion_id="AC-003",
                title="Currency conversion",
                given="foreign currency",
                when="charge processed",
                then="correct rate applied",
            ),
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="security", description="PCI-DSS compliant")
        ],
        out_of_scope=["Crypto payments"],
    )


def _create_sample_plan(spec_id: object) -> ImplementationPlan:
    from uuid import UUID

    return ImplementationPlan(
        spec_id=UUID(str(spec_id)),
        technical_summary="Payment tech summary",
        impacted_files=["src/payment.py"],
        tasks=[
            DecomposedTask(
                task_id="TASK-001",
                title="Implement payment",
                description="Core payment",
                target_files=["src/payment.py"],
            )
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Traceability Matrix Builder Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTraceabilityMatrixBuilder:
    def test_extracts_function_names(
        self, matrix_builder: TraceabilityMatrixBuilder
    ) -> None:
        code = (
            "def test_charge_success():\n"
            "    pass\n\n"
            "class TestSuite:\n"
            "    def test_insufficient_funds(self):\n"
            "        pass\n"
        )
        funcs = matrix_builder.extract_test_functions(code)
        assert funcs == ["test_charge_success", "test_insufficient_funds"]

    def test_bidirectional_mapping_complete(
        self, matrix_builder: TraceabilityMatrixBuilder
    ) -> None:
        spec = _create_sample_spec()
        tests = [
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="Test for AC-001",
                source_criterion_id="AC-001",
                file_path="tests/test_unit.py",
                source_code="def test_charge_success(): assert True\n",
            ),
            SynthesizedTest(
                test_id="TEST-002",
                test_type="integration",
                description="Test for AC-002",
                source_criterion_id="AC-002",
                file_path="tests/test_integration.py",
                source_code="def test_insufficient_funds(): assert True\n",
            ),
            SynthesizedTest(
                test_id="TEST-003",
                test_type="acceptance",
                description="Test for AC-003",
                source_criterion_id="AC-003",
                file_path="tests/test_acceptance.py",
                source_code="def test_currency_conversion(): assert True\n",
            ),
        ]

        matrix = matrix_builder.build(spec, tests)

        assert matrix.coverage_ratio == 1.0
        assert len(matrix.uncovered_criteria) == 0

        # Criterion -> Tests
        assert matrix.criterion_to_tests["AC-001"] == ["test_charge_success"]
        assert matrix.criterion_to_tests["AC-002"] == ["test_insufficient_funds"]
        assert matrix.criterion_to_tests["AC-003"] == ["test_currency_conversion"]

        # Test -> Criteria
        assert matrix.test_to_criteria["test_charge_success"] == ["AC-001"]
        assert matrix.test_to_criteria["test_insufficient_funds"] == ["AC-002"]
        assert matrix.test_to_criteria["test_currency_conversion"] == ["AC-003"]

    def test_detects_uncovered_criteria_and_orphans(
        self, matrix_builder: TraceabilityMatrixBuilder
    ) -> None:
        spec = _create_sample_spec()
        # Only covers AC-001 and has an orphan test
        tests = [
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="Unit test AC-001",
                source_criterion_id="AC-001",
                file_path="tests/test_unit.py",
                source_code="def test_ac1(): pass\n",
            ),
            SynthesizedTest(
                test_id="TEST-999",
                test_type="unit",
                description="General utility test",
                source_criterion_id=None,
                file_path="tests/test_utils.py",
                source_code="def test_helper(): pass\n",
            ),
        ]

        matrix = matrix_builder.build(spec, tests)

        assert matrix.coverage_ratio < 1.0
        assert "AC-002" in matrix.uncovered_criteria
        assert "AC-003" in matrix.uncovered_criteria
        assert any("test_helper" in ot for ot in matrix.orphan_tests)

    def test_render_matrix_markdown(
        self, matrix_builder: TraceabilityMatrixBuilder
    ) -> None:
        spec = _create_sample_spec()
        tests = [
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="AC-001 test",
                source_criterion_id="AC-001",
                file_path="tests/test_unit.py",
                source_code="def test_ac001(): pass\n",
            )
        ]
        matrix = matrix_builder.build(spec, tests)
        md = matrix.render_matrix_markdown()

        assert "Acceptance Criteria Traceability Matrix" in md
        assert "AC-001" in md
        assert "AC-002" in md
        assert "✅ Covered" in md
        assert "❌ Missing" in md


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Test Generator Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestGeneratorSuite:
    def test_generates_and_materializes_tests(self, tmp_path: Path) -> None:
        mock_llm = MockProvider(LLMConfig(provider="mock"))
        generator = TestGenerator(llm=mock_llm)

        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        implementation = ImplementationOutput(
            plan_id=plan.plan_id,
            changes=[
                FileChange(
                    path="src/payment.py",
                    action="create",
                    content="def pay(): return True\n",
                )
            ],
        )

        output = generator.generate(
            spec=spec,
            plan=plan,
            implementation=implementation,
            sandbox_root=tmp_path,
        )

        # 1. Verify test generation output
        assert len(output.tests) >= 3
        assert "Acceptance Criteria Traceability Matrix" in output.coverage_notes

        # 2. Verify conftest.py with sys.path injection
        conftest = tmp_path / "tests" / "conftest.py"
        assert conftest.is_file()
        conftest_content = conftest.read_text(encoding="utf-8")
        assert "sys.path.insert" in conftest_content
        assert "SRC_DIR" in conftest_content

        # 3. Verify tests/__init__.py
        assert (tmp_path / "tests" / "__init__.py").is_file()

        # 4. Verify test files materialized
        test_files = list((tmp_path / "tests").glob("test_*.py"))
        assert len(test_files) >= 1

    def test_guarantees_100_percent_ac_coverage_with_fallback(self) -> None:
        # LLM returns an empty test list
        class IncompleteLLM(BaseLLMProvider):
            def generate(
                self,
                prompt: str,
                *,
                system_prompt: str = "",
                temperature: float | None = None,
            ) -> tuple[str, TokenUsage]:
                import json

                return json.dumps({"tests": [], "coverage_notes": "None"}), TokenUsage()

        generator = TestGenerator(llm=IncompleteLLM(LLMConfig(provider="mock")))
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        implementation = ImplementationOutput(plan_id=plan.plan_id, changes=[])

        output = generator.generate(spec, plan, implementation)

        # Fallback generated for all 3 criteria (AC-001, AC-002, AC-003)
        assert len(output.tests) == 3
        test_acs = {t.source_criterion_id for t in output.tests}
        assert test_acs == {"AC-001", "AC-002", "AC-003"}
        assert "100%" in output.coverage_notes
