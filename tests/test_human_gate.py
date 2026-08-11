"""Tests for two-stage human governance approval checkpoints and HMAC-SHA256 signatures."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from spec_pipeline.core.exceptions import ApprovalRejectedError
from spec_pipeline.core.models import (
    AcceptanceCriterion,
    ApprovalDecision,
    ApprovalStatus,
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
    UserStory,
)
from spec_pipeline.governance.human_gate import HumanApprovalGate


@pytest.fixture
def gate() -> HumanApprovalGate:
    return HumanApprovalGate(signing_secret="test-secret-key-12345")


def _create_sample_spec() -> FeatureSpec:
    return FeatureSpec(
        title="Payment Service",
        objective="Process payments",
        user_stories=[UserStory(as_a="u", i_want="w", so_that="t")],
        business_rules=[BusinessRule(rule_id="BR-001", description="Must validate")],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="t",
                given="g",
                when="w",
                then="th",
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="sec", description="PCI")
        ],
        out_of_scope=["Out"],
    )


def _create_sample_plan() -> ImplementationPlan:
    return ImplementationPlan(
        spec_id=uuid4(),
        technical_summary="Technical architecture summary",
        architecture_decisions=["ADR-001: Use hexagonal architecture"],
        impacted_files=["src/payment.py"],
        tasks=[
            DecomposedTask(
                task_id="TASK-001",
                title="T1",
                description="desc",
                target_files=["src/payment.py"],
            )
        ],
        risks=[
            EvaluatedRisk(
                risk_id="RISK-001",
                category="security",
                description="Sensitive data",
                likelihood="medium",
                impact="high",
                mitigation="Use TLS",
            )
        ],
    )


def _create_sample_evidence(plan_id: object) -> tuple[ImplementationOutput, QualityGateSuiteResult]:
    from uuid import UUID

    pid = UUID(str(plan_id))
    impl = ImplementationOutput(
        plan_id=pid,
        changes=[
            FileChange(
                path="src/payment.py",
                action="create",
                content="def pay(): pass\n",
                diff_summary="Created payment module",
            )
        ],
    )
    gates = [
        QualityGateResult(gate_name="syntax", passed=True, duration_seconds=0.01),
        QualityGateResult(gate_name="lint", passed=True, duration_seconds=0.05),
        QualityGateResult(gate_name="typecheck", passed=True, duration_seconds=0.1),
        QualityGateResult(gate_name="security", passed=True, duration_seconds=0.02),
        QualityGateResult(gate_name="pytest", passed=True, duration_seconds=0.2),
        QualityGateResult(gate_name="acceptance_criteria", passed=True, duration_seconds=0.01),
    ]
    suite = QualityGateSuiteResult(
        plan_id=pid,
        gates=gates,
        all_passed=True,
    )
    return impl, suite


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Checkpoint #1: Pre-Implementation Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPreImplementationApproval:
    def test_auto_approve_mode(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()

        decision = gate.request_pre_implementation_approval(
            spec=spec,
            plan=plan,
            auto_approve=True,
            reviewer="Alice",
            comments="Approved by CI",
        )

        assert decision.checkpoint == "pre-implementation"
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.reviewer == "Alice"
        assert decision.comments == "Approved by CI"
        assert decision.signature != ""
        assert decision.decided_at is not None

        # Verify HMAC signature
        assert gate.verify_signature(
            decision, payload_hash=spec.spec_hash or str(plan.plan_id)
        ) is True

    def test_interactive_approval_accepted(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()

        with patch("rich.prompt.Confirm.ask", return_value=True):
            decision = gate.request_pre_implementation_approval(
                spec=spec,
                plan=plan,
                auto_approve=False,
                reviewer="Bob",
            )

        assert decision.status == ApprovalStatus.APPROVED
        assert decision.reviewer == "Bob"

    def test_interactive_approval_rejected(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()

        with (
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch("rich.prompt.Prompt.ask", return_value="High blast radius"),
            pytest.raises(ApprovalRejectedError) as exc_info,
        ):
            gate.request_pre_implementation_approval(
                spec=spec,
                plan=plan,
                auto_approve=False,
                reviewer="Charlie",
            )

        assert "pre-implementation" in str(exc_info.value)
        assert "High blast radius" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Checkpoint #2: Pre-Merge Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPreMergeApproval:
    def test_auto_approve_mode(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()
        impl, suite = _create_sample_evidence(plan.plan_id)

        decision = gate.request_pre_merge_approval(
            spec=spec,
            plan=plan,
            implementation=impl,
            quality_suite=suite,
            auto_approve=True,
            reviewer="Release Officer",
            comments="100% test passing",
        )

        assert decision.checkpoint == "pre-merge"
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.reviewer == "Release Officer"
        assert decision.signature != ""
        assert gate.verify_signature(decision, payload_hash=str(plan.plan_id)) is True

    def test_interactive_approval_accepted(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()
        impl, suite = _create_sample_evidence(plan.plan_id)

        with patch("rich.prompt.Confirm.ask", return_value=True):
            decision = gate.request_pre_merge_approval(
                spec=spec,
                plan=plan,
                implementation=impl,
                quality_suite=suite,
                auto_approve=False,
            )

        assert decision.status == ApprovalStatus.APPROVED

    def test_interactive_approval_rejected(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()
        impl, suite = _create_sample_evidence(plan.plan_id)

        with (
            patch("rich.prompt.Confirm.ask", return_value=False),
            patch("rich.prompt.Prompt.ask", return_value="Fails staging tests"),
            pytest.raises(ApprovalRejectedError) as exc_info,
        ):
            gate.request_pre_merge_approval(
                spec=spec,
                plan=plan,
                implementation=impl,
                quality_suite=suite,
                auto_approve=False,
            )

        assert "pre-merge" in str(exc_info.value)
        assert "Fails staging tests" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────────────
# 3.  HMAC-SHA256 Cryptographic Signature Verification Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCryptographicSignatures:
    def test_tampered_decision_fails_verification(
        self, gate: HumanApprovalGate
    ) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()

        decision = gate.request_pre_implementation_approval(
            spec=spec,
            plan=plan,
            auto_approve=True,
            reviewer="Legitimate Reviewer",
        )

        # Original passes
        assert gate.verify_signature(
            decision, payload_hash=spec.spec_hash or str(plan.plan_id)
        ) is True

        # Tampered reviewer
        tampered_decision = ApprovalDecision(
            checkpoint=decision.checkpoint,
            status=decision.status,
            reviewer="Imposter",
            comments=decision.comments,
            signature=decision.signature,
            decided_at=decision.decided_at,
        )
        assert gate.verify_signature(
            tampered_decision, payload_hash=spec.spec_hash or str(plan.plan_id)
        ) is False

    def test_tampered_payload_hash_fails(self, gate: HumanApprovalGate) -> None:
        spec = _create_sample_spec()
        plan = _create_sample_plan()

        decision = gate.request_pre_implementation_approval(
            spec=spec,
            plan=plan,
            auto_approve=True,
            reviewer="Alice",
        )

        # Verified with wrong payload hash
        assert gate.verify_signature(decision, payload_hash="tampered-hash") is False
