"""End-to-end Spec-Driven Development Pipeline Orchestrator coordinating all 7 stages."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from spec_pipeline.audit.logger import AuditLogger
from spec_pipeline.audit.provenance import SLSAProvenanceBuilder
from spec_pipeline.audit.reporter import AuditReporter
from spec_pipeline.governance.human_gate import HumanApprovalGate
from spec_pipeline.governance.sandbox_policy import SandboxPolicyEnforcer
from spec_pipeline.implementation.patch_engine import PatchEngine
from spec_pipeline.implementation.synthesizer import CodeSynthesizer
from spec_pipeline.llm import get_llm_provider
from spec_pipeline.planning.planner import Planner
from spec_pipeline.quality_gates.runner import QualityGateRunner
from spec_pipeline.spec_intake.parser import SpecParser
from spec_pipeline.spec_intake.validator import SpecValidator
from spec_pipeline.testing.test_generator import TestGenerator

if TYPE_CHECKING:
    from spec_pipeline.core.models import (
        ApprovalDecision,
        AuditRecord,
        FeatureSpec,
        ImplementationOutput,
        ImplementationPlan,
        QualityGateSuiteResult,
        TestGenerationOutput,
    )
    from spec_pipeline.llm.base import BaseLLMProvider


@dataclass
class PipelineOrchestratorResult:
    """Consolidated outputs of a complete end-to-end pipeline run."""

    spec: FeatureSpec
    plan: ImplementationPlan
    checkpoint_1: ApprovalDecision
    implementation: ImplementationOutput
    test_generation: TestGenerationOutput
    quality_results: QualityGateSuiteResult
    checkpoint_2: ApprovalDecision
    audit_record: AuditRecord
    provenance: dict[str, Any]
    report_markdown: str
    dashboard_html: str
    artifacts_dir: Path | None = None


class PipelineOrchestrator:
    """Orchestrates all 7 stages of the AI-native spec-driven development lifecycle."""

    def __init__(
        self,
        provider: BaseLLMProvider | None = None,
        provider_type: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        signing_secret: str | None = None,
        console: Console | None = None,
    ) -> None:
        self.console = console or Console()
        self.provider = provider or get_llm_provider(
            provider_type=provider_type,
            api_key=api_key,
            model_name=model_name,
        )

        self.parser = SpecParser()
        self.validator = SpecValidator()
        self.planner = Planner(llm=self.provider)
        self.human_gate = HumanApprovalGate(
            signing_secret=signing_secret,
            console=self.console,
        )
        self.sandbox_enforcer = SandboxPolicyEnforcer()
        self.patch_engine = PatchEngine()
        self.synthesizer = CodeSynthesizer(
            llm=self.provider,
            policy_enforcer=self.sandbox_enforcer,
            patch_engine=self.patch_engine,
        )
        self.test_generator = TestGenerator(llm=self.provider)
        self.quality_runner = QualityGateRunner()
        self.audit_logger = AuditLogger()
        self.provenance_builder = SLSAProvenanceBuilder()
        self.reporter = AuditReporter()

    # ── Stage-by-Stage Granular Methods ───────────────────────────────────── #

    def stage_intake(
        self, spec_path_or_content: str | Path, fmt: str | None = None
    ) -> FeatureSpec:
        """Stage 1: Ingest, compute fingerprint, and validate 6-section schema."""
        if isinstance(spec_path_or_content, Path) or (
            isinstance(spec_path_or_content, str) and Path(spec_path_or_content).is_file()
        ):
            spec = self.parser.parse_file(Path(spec_path_or_content))
        else:
            raw_text = str(spec_path_or_content).strip()
            fmt_lower = (fmt or "").lower()
            if fmt_lower == "json" or (not fmt and raw_text.startswith("{")):
                spec = self.parser.parse_json(raw_text)
            elif (
                fmt_lower in {"yaml", "yml"}
                or (
                    not fmt
                    and ("objective:" in raw_text or "title:" in raw_text)
                    and not raw_text.startswith("#")
                )
            ):
                spec = self.parser.parse_yaml(raw_text)
            else:
                spec = self.parser.parse_markdown(raw_text)

        self.validator.validate_or_raise(spec)
        return spec

    def stage_plan(
        self, spec_path_or_content: str | Path, fmt: str | None = None
    ) -> tuple[FeatureSpec, ImplementationPlan, AuditRecord]:
        """Stage 1 + Stage 2: Ingest spec and generate technical implementation plan."""
        spec = self.stage_intake(spec_path_or_content, fmt=fmt)
        record = self.audit_logger.create_record(spec)

        plan = self.planner.plan(spec)
        self.audit_logger.log_plan(record, plan)
        return spec, plan, record

    def stage_implement_and_verify(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        sandbox_dir: Path,
        record: AuditRecord,
    ) -> tuple[ImplementationOutput, TestGenerationOutput, QualityGateSuiteResult]:
        """Stage 4-6: Code synthesis, test generation, and deterministic quality verification."""
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        # 4. Code Synthesis
        implementation = self.synthesizer.synthesize(
            spec=spec,
            plan=plan,
            sandbox_root=sandbox_dir,
        )
        self.audit_logger.log_implementation(record, implementation)

        # 5. Test Generation
        test_generation = self.test_generator.generate(
            spec=spec,
            plan=plan,
            implementation=implementation,
            sandbox_root=sandbox_dir,
        )
        self.audit_logger.log_test_generation(record, test_generation)

        # 6. Quality Gate Verification
        quality_results = self.quality_runner.execute_all_gates(
            sandbox_root=sandbox_dir,
            spec=spec,
            plan=plan,
            tests=test_generation.tests,
            raise_on_failure=False,
        )
        self.audit_logger.log_quality_results(record, quality_results)

        return implementation, test_generation, quality_results

    def stage_finalize_merge(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        implementation: ImplementationOutput,
        quality_suite: QualityGateSuiteResult,
        record: AuditRecord,
        artifacts_dir: Path | None = None,
        auto_approve: bool = True,
        reviewer: str = "Release Lead",
        comments: str = "",
    ) -> tuple[ApprovalDecision, dict[str, Any], str, str]:
        """Stage 7: Pre-merge governance, audit sealing, SLSA provenance, and dashboards."""
        decision_2 = self.human_gate.request_pre_merge_approval(
            spec=spec,
            plan=plan,
            implementation=implementation,
            quality_suite=quality_suite,
            auto_approve=auto_approve,
            reviewer=reviewer,
            comments=comments,
        )
        self.audit_logger.log_approval(record, decision_2)

        if artifacts_dir:
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            self.audit_logger.finalize_record(record, output_dir=artifacts_dir)
            prov_file = artifacts_dir / "provenance.json"
            report_file = artifacts_dir / "audit_report.md"
            dash_file = artifacts_dir / "dashboard.html"
        else:
            record.completed_at = datetime.now(UTC)
            prov_file = None
            report_file = None
            dash_file = None

        provenance = self.provenance_builder.generate_provenance(
            record, output_file=prov_file
        )
        report_md = self.reporter.generate_markdown_report(
            record, output_file=report_file
        )
        dashboard_html = self.reporter.generate_html_dashboard(
            record, output_file=dash_file
        )

        return decision_2, provenance, report_md, dashboard_html

    # ── Full End-to-End Orchestration ─────────────────────────────────────── #

    def run_pipeline(
        self,
        spec_path_or_content: str | Path,
        sandbox_dir: str | Path | None = None,
        artifacts_dir: str | Path | None = None,
        auto_approve: bool = False,
        reviewer: str = "Lead Engineer",
        spec_format: str | None = None,
    ) -> PipelineOrchestratorResult:
        """Run all 7 lifecycle stages deterministically from end-to-end."""
        # 1. Spec Intake & Validation
        spec, plan, record = self.stage_plan(spec_path_or_content, fmt=spec_format)

        # 2. Checkpoint #1: Pre-Implementation Approval
        decision_1 = self.human_gate.request_pre_implementation_approval(
            spec=spec,
            plan=plan,
            auto_approve=auto_approve,
            reviewer=reviewer,
        )
        self.audit_logger.log_approval(record, decision_1)

        # Sandbox management
        if sandbox_dir is not None:
            sb_path = Path(sandbox_dir).resolve()
            sb_path.mkdir(parents=True, exist_ok=True)
        else:
            temp_dir = tempfile.mkdtemp(prefix="spec_sandbox_")
            sb_path = Path(temp_dir).resolve()

        art_path = Path(artifacts_dir).resolve() if artifacts_dir else None

        # 3. AI Code Synthesis & Test Generation & Quality Verification
        impl, tests_out, quality_results = self.stage_implement_and_verify(
            spec=spec,
            plan=plan,
            sandbox_dir=sb_path,
            record=record,
        )

        # 4. Checkpoint #2: Pre-Merge Approval, SLSA Provenance & Dashboards
        decision_2, provenance, report_md, dashboard_html = self.stage_finalize_merge(
            spec=spec,
            plan=plan,
            implementation=impl,
            quality_suite=quality_results,
            record=record,
            artifacts_dir=art_path,
            auto_approve=auto_approve,
            reviewer=reviewer,
        )

        return PipelineOrchestratorResult(
            spec=spec,
            plan=plan,
            checkpoint_1=decision_1,
            implementation=impl,
            test_generation=tests_out,
            quality_results=quality_results,
            checkpoint_2=decision_2,
            audit_record=record,
            provenance=provenance,
            report_markdown=report_md,
            dashboard_html=dashboard_html,
            artifacts_dir=art_path,
        )
