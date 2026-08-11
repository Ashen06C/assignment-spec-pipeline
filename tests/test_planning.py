"""Tests for the planning layer — task decomposition, DAG ordering, and risk analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec_pipeline.core.models import (
    AcceptanceCriterion,
    BusinessRule,
    DecomposedTask,
    FeatureSpec,
    ImplementationPlan,
    NonFunctionalRequirement,
    UserStory,
)
from spec_pipeline.llm import LLMConfig, MockProvider
from spec_pipeline.planning.planner import Planner, order_tasks_dag
from spec_pipeline.planning.risk_analyzer import RiskAnalyzer
from spec_pipeline.spec_intake.parser import SpecParser

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples" / "specs"


@pytest.fixture
def parser() -> SpecParser:
    return SpecParser()


@pytest.fixture
def risk_analyzer() -> RiskAnalyzer:
    return RiskAnalyzer()


@pytest.fixture
def mock_planner() -> Planner:
    mock_llm = MockProvider(LLMConfig(provider="mock"))
    return Planner(llm=mock_llm)


def _create_minimal_spec(
    title: str = "Test Feature",
    objective: str = "Implement test feature",
    extra_corpus: str = "",
) -> FeatureSpec:
    """Helper to construct a valid FeatureSpec."""
    return FeatureSpec(
        title=title,
        objective=f"{objective} {extra_corpus}",
        user_stories=[
            UserStory(
                as_a="developer",
                i_want="a reliable pipeline",
                so_that="delivery is smooth",
            )
        ],
        business_rules=[
            BusinessRule(rule_id="BR-001", description="Must follow specs.")
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="Verify feature",
                given="valid input",
                when="executed",
                then="success",
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(
                category="performance",
                description=f"Standard performance {extra_corpus}",
            )
        ],
        out_of_scope=["Out of scope item"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Task DAG Ordering Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTaskDAGOrdering:
    def test_linear_dependency_chain(self) -> None:
        tasks = [
            DecomposedTask(
                task_id="TASK-003",
                title="T3",
                description="desc",
                dependencies=["TASK-002"],
            ),
            DecomposedTask(
                task_id="TASK-001",
                title="T1",
                description="desc",
                dependencies=[],
            ),
            DecomposedTask(
                task_id="TASK-002",
                title="T2",
                description="desc",
                dependencies=["TASK-001"],
            ),
        ]
        ordered = order_tasks_dag(tasks)
        ordered_ids = [t.task_id for t in ordered]
        assert ordered_ids == ["TASK-001", "TASK-002", "TASK-003"]

    def test_branching_dag(self) -> None:
        tasks = [
            DecomposedTask(
                task_id="TASK-004",
                title="T4",
                description="desc",
                dependencies=["TASK-002", "TASK-003"],
            ),
            DecomposedTask(
                task_id="TASK-002",
                title="T2",
                description="desc",
                dependencies=["TASK-001"],
            ),
            DecomposedTask(
                task_id="TASK-003",
                title="T3",
                description="desc",
                dependencies=["TASK-001"],
            ),
            DecomposedTask(
                task_id="TASK-001",
                title="T1",
                description="desc",
                dependencies=[],
            ),
        ]
        ordered = order_tasks_dag(tasks)
        ordered_ids = [t.task_id for t in ordered]

        # TASK-001 must be first
        assert ordered_ids[0] == "TASK-001"
        # TASK-004 must be last
        assert ordered_ids[-1] == "TASK-004"
        # TASK-002 and TASK-003 must be before TASK-004
        assert ordered_ids.index("TASK-002") < ordered_ids.index("TASK-004")
        assert ordered_ids.index("TASK-003") < ordered_ids.index("TASK-004")

    def test_cycle_resilience(self) -> None:
        tasks = [
            DecomposedTask(
                task_id="TASK-001",
                title="T1",
                description="desc",
                dependencies=["TASK-002"],
            ),
            DecomposedTask(
                task_id="TASK-002",
                title="T2",
                description="desc",
                dependencies=["TASK-001"],
            ),
            DecomposedTask(
                task_id="TASK-003",
                title="T3",
                description="desc",
                dependencies=[],
            ),
        ]
        ordered = order_tasks_dag(tasks)
        # All tasks must still be present without data loss
        assert len(ordered) == 3
        # TASK-003 has no dependencies so it should be scheduled first
        assert ordered[0].task_id == "TASK-003"


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Risk Analyzer Rule Heuristics Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestRiskAnalyzerHeuristics:
    def test_detects_concurrency_risk(self, risk_analyzer: RiskAnalyzer) -> None:
        spec = _create_minimal_spec(
            title="Rate Limiter",
            objective="Implement high-volume rate limiting with atomic locks and thread safety.",
        )
        risks = risk_analyzer.analyze(spec)
        concurrency_risks = [r for r in risks if r.category == "concurrency"]
        assert len(concurrency_risks) >= 1
        assert "race condition" in concurrency_risks[0].description.lower()
        assert concurrency_risks[0].mitigation != ""

    def test_detects_security_risk(self, risk_analyzer: RiskAnalyzer) -> None:
        spec = _create_minimal_spec(
            title="Auth Service",
            objective="Store encrypted credentials, passwords, and sensitive PII tokens.",
        )
        risks = risk_analyzer.analyze(spec)
        security_risks = [r for r in risks if r.category == "security"]
        assert len(security_risks) >= 1
        desc = security_risks[0].description.lower()
        assert "cryptographic" in desc or "sensitive" in desc
        assert security_risks[0].impact in {"medium", "high"}

    def test_detects_performance_risk(self, risk_analyzer: RiskAnalyzer) -> None:
        spec = _create_minimal_spec(
            title="High Throughput Ingestion",
            objective=(
                "Process 50,000 requests per minute with p99 latency "
                "under 5ms using caching."
            ),
        )
        risks = risk_analyzer.analyze(spec)
        perf_risks = [r for r in risks if r.category == "performance"]
        assert len(perf_risks) >= 1
        desc = perf_risks[0].description.lower()
        assert "latency" in desc or "throughput" in desc

    def test_detects_blast_radius_risk(self, risk_analyzer: RiskAnalyzer) -> None:
        spec = _create_minimal_spec()
        many_files = [
            "src/models/a.py",
            "src/models/b.py",
            "src/services/c.py",
            "src/services/d.py",
            "src/api/e.py",
        ]
        risks = risk_analyzer.analyze(spec, impacted_files=many_files)
        blast_risks = [r for r in risks if r.category == "blast_radius"]
        assert len(blast_risks) == 1
        assert "alters 5 files" in blast_risks[0].description

    def test_all_example_specs_generate_risks(
        self, parser: SpecParser, risk_analyzer: RiskAnalyzer
    ) -> None:
        rate_limiter = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        token_bucket = parser.parse_file(EXAMPLES_DIR / "token_bucket_limiter.yaml")
        audit_logger = parser.parse_file(EXAMPLES_DIR / "audit_logger_service.json")

        for s in [rate_limiter, token_bucket, audit_logger]:
            risks = risk_analyzer.analyze(s)
            assert len(risks) >= 1
            for r in risks:
                assert r.mitigation != ""
                assert r.likelihood in {"low", "medium", "high"}
                assert r.impact in {"low", "medium", "high"}


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Planner Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPlanner:
    def test_plan_generation_from_spec(
        self, parser: SpecParser, mock_planner: Planner
    ) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "rate_limiter.md")
        plan = mock_planner.plan(spec)

        assert isinstance(plan, ImplementationPlan)
        assert plan.spec_id == spec.spec_id
        assert len(plan.tasks) >= 3
        assert len(plan.impacted_files) >= 1
        assert len(plan.architecture_decisions) >= 1
        assert len(plan.risks) >= 1

        # Check task target_files
        for task in plan.tasks:
            assert task.task_id.startswith("TASK-")
            assert len(task.target_files) >= 1

        # Check test strategy coverage of ACs
        for ac in spec.acceptance_criteria:
            assert ac.criterion_id in plan.test_strategy.acceptance_test_mapping

    def test_plan_architecture_decisions(
        self, parser: SpecParser, mock_planner: Planner
    ) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "token_bucket_limiter.yaml")
        plan = mock_planner.plan(spec)

        assert any("ADR-" in adr for adr in plan.architecture_decisions)

    def test_plan_preserves_task_order(
        self, parser: SpecParser, mock_planner: Planner
    ) -> None:
        spec = parser.parse_file(EXAMPLES_DIR / "audit_logger_service.json")
        plan = mock_planner.plan(spec)

        # Ensure dependencies come before dependents
        task_indices = {t.task_id: idx for idx, t in enumerate(plan.tasks)}
        for task in plan.tasks:
            for dep in task.dependencies:
                if dep in task_indices:
                    assert task_indices[dep] < task_indices[task.task_id]
