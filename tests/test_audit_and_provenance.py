"""Tests for audit logging, SLSA v0.2 provenance generation, and visual reporting."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from spec_pipeline.audit.logger import AuditLogger
from spec_pipeline.audit.provenance import SLSAProvenanceBuilder
from spec_pipeline.audit.reporter import AuditReporter
from spec_pipeline.core.models import (
    AcceptanceCriterion,
    ApprovalDecision,
    ApprovalStatus,
    AuditRecord,
    BusinessRule,
    DecomposedTask,
    EvaluatedRisk,
    FeatureSpec,
    FileChange,
    ImplementationOutput,
    ImplementationPlan,
    NonFunctionalRequirement,
    QualityGateResult,
    QualityGateSuiteResult,
    SynthesizedTest,
    TestGenerationOutput,
    UserStory,
)
from spec_pipeline.llm.base import TokenUsage


@pytest.fixture
def logger() -> AuditLogger:
    return AuditLogger()


@pytest.fixture
def provenance_builder() -> SLSAProvenanceBuilder:
    return SLSAProvenanceBuilder()


@pytest.fixture
def reporter() -> AuditReporter:
    return AuditReporter()


def _create_sample_spec() -> FeatureSpec:
    return FeatureSpec(
        title="Token Bucket Limiter",
        objective="Rate limiting via token bucket algorithm",
        user_stories=[
            UserStory(as_a="client", i_want="fair rate limits", so_that="service stays up")
        ],
        business_rules=[BusinessRule(rule_id="BR-001", description="100 tokens max")],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="Consume token",
                given="bucket with tokens",
                when="consume called",
                then="tokens decremented",
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="performance", description="< 1ms latency")
        ],
        out_of_scope=["Distributed Redis sync in v1"],
    )


def _create_sample_plan(spec_id: object) -> ImplementationPlan:
    from uuid import UUID

    return ImplementationPlan(
        spec_id=UUID(str(spec_id)),
        technical_summary="Token bucket technical summary",
        architecture_decisions=["ADR-001: Thread-safe in-memory token bucket"],
        impacted_files=["src/limiter.py"],
        tasks=[
            DecomposedTask(
                task_id="TASK-001",
                title="Implement bucket",
                description="Core logic",
                target_files=["src/limiter.py"],
            )
        ],
        risks=[
            EvaluatedRisk(
                risk_id="RISK-001",
                category="concurrency",
                description="Race condition on token refill",
                likelihood="medium",
                impact="high",
                mitigation="Use threading.Lock",
            )
        ],
    )


def _populate_full_audit_record(
    logger: AuditLogger, spec: FeatureSpec, plan: ImplementationPlan
) -> AuditRecord:
    record = logger.create_record(spec)
    logger.log_plan(record, plan)

    logger.log_llm_interaction(
        record,
        stage="planning",
        prompt="Planning prompt",
        response="Planning response",
        model="mock-model",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )

    impl = ImplementationOutput(
        plan_id=plan.plan_id,
        changes=[
            FileChange(
                path="src/limiter.py",
                action="create",
                content="class Limiter:\n    pass\n",
                diff_summary="Created limiter class",
            )
        ],
    )
    logger.log_implementation(record, impl)

    tests_out = TestGenerationOutput(
        plan_id=plan.plan_id,
        tests=[
            SynthesizedTest(
                test_id="TEST-001",
                test_type="unit",
                description="Test limiter",
                source_criterion_id="AC-001",
                file_path="tests/test_limiter.py",
                source_code="def test_bucket(): assert True\n",
            )
        ],
    )
    logger.log_test_generation(record, tests_out)

    logger.log_approval(
        record,
        ApprovalDecision(
            checkpoint="pre-implementation",
            status=ApprovalStatus.APPROVED,
            reviewer="Lead Architect",
            signature="sig1234567890",
        ),
    )

    logger.log_quality_results(
        record,
        QualityGateSuiteResult(
            plan_id=plan.plan_id,
            gates=[
                QualityGateResult(gate_name="syntax", passed=True, duration_seconds=0.01),
                QualityGateResult(gate_name="pytest", passed=True, duration_seconds=0.1),
            ],
            all_passed=True,
        ),
    )

    return record


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Audit Logger Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestAuditLogger:
    def test_full_lifecycle_logging(self, logger: AuditLogger, tmp_path: Path) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)

        record = _populate_full_audit_record(logger, spec, plan)
        finalized = logger.finalize_record(record, output_dir=tmp_path)

        assert finalized.completed_at is not None
        assert len(finalized.llm_interactions) == 1
        assert len(finalized.generated_outputs) == 2
        assert len(finalized.approvals) == 1
        assert finalized.quality_results is not None

        # Verify disk file written
        output_file = tmp_path / f"audit_record_{record.run_id}.json"
        assert output_file.is_file()
        saved_data = json.loads(output_file.read_text(encoding="utf-8"))
        assert saved_data["run_id"] == str(record.run_id)

    def test_compute_integrity_hash(self, logger: AuditLogger) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        record = _populate_full_audit_record(logger, spec, plan)

        h1 = logger.compute_integrity_hash(record)
        h2 = logger.compute_integrity_hash(record)
        assert len(h1) == 64
        assert h1 == h2


# ──────────────────────────────────────────────────────────────────────────────
# 2.  SLSA v0.2 Provenance Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSLSAProvenance:
    def test_generates_valid_in_toto_statement(
        self,
        logger: AuditLogger,
        provenance_builder: SLSAProvenanceBuilder,
        tmp_path: Path,
    ) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        record = _populate_full_audit_record(logger, spec, plan)
        logger.finalize_record(record)

        prov_file = tmp_path / "provenance.json"
        statement = provenance_builder.generate_provenance(record, output_file=prov_file)

        # In-Toto headers
        assert statement["_type"] == "https://in-toto.io/Statement/v0.1"
        assert statement["predicateType"] == "https://slsa.dev/provenance/v0.2"

        # Subjects
        assert len(statement["subject"]) >= 1
        assert statement["subject"][0]["name"] == "src/limiter.py"
        assert "sha256" in statement["subject"][0]["digest"]

        # Predicate metadata
        predicate = statement["predicate"]
        assert "spec-pipeline.ai" in predicate["builder"]["id"]
        assert len(predicate["materials"]) >= 1
        assert len(predicate["approvals"]) == 1
        assert predicate["qualityVerification"]["all_passed"] is True

        # File written
        assert prov_file.is_file()


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Audit Reporter Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestAuditReporter:
    def test_generate_markdown_report(
        self, logger: AuditLogger, reporter: AuditReporter, tmp_path: Path
    ) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        record = _populate_full_audit_record(logger, spec, plan)
        logger.finalize_record(record)

        report_file = tmp_path / "audit_report.md"
        report_md = reporter.generate_markdown_report(record, output_file=report_file)

        assert "# Spec-Driven Pipeline Audit Report" in report_md
        assert "Token Bucket Limiter" in report_md
        assert "TASK-001" in report_md
        assert "RISK-001" in report_md
        assert "src/limiter.py" in report_md
        assert "syntax" in report_md
        assert report_file.is_file()

    def test_generate_html_dashboard(
        self, logger: AuditLogger, reporter: AuditReporter, tmp_path: Path
    ) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan(spec.spec_id)
        record = _populate_full_audit_record(logger, spec, plan)
        logger.finalize_record(record)

        dash_file = tmp_path / "dashboard.html"
        html = reporter.generate_html_dashboard(record, output_file=dash_file)

        assert "<!DOCTYPE html>" in html
        assert "Token Bucket Limiter" in html
        assert "status-pill" in html
        assert "metric-card" in html
        assert "TASK-001" in html
        assert "RISK-001" in html
        assert "sig1234567890" in html
        assert dash_file.is_file()
