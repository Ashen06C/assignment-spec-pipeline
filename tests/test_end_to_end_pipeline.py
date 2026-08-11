"""Full End-to-End Integration and CLI test suites for the Spec-Driven Pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from spec_pipeline.cli.main import app
from spec_pipeline.core.models import ApprovalStatus
from spec_pipeline.orchestrator import PipelineOrchestrator

runner = CliRunner()


# ──────────────────────────────────────────────────────────────────────────────
# 1.  End-to-End Pipeline Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEndToEndPipeline:
    def test_e2e_yaml_spec_run(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = repo_root / "examples" / "specs" / "token_bucket_limiter.yaml"
        sandbox_dir = tmp_path / "sandbox"
        artifacts_dir = tmp_path / "artifacts"

        orchestrator = PipelineOrchestrator(provider_type="mock")
        res = orchestrator.run_pipeline(
            spec_path_or_content=spec_file,
            sandbox_dir=sandbox_dir,
            artifacts_dir=artifacts_dir,
            auto_approve=True,
            reviewer="CI Lead",
        )

        # 1. Stage 1: Spec Intake
        assert res.spec.title == "Token Bucket Rate Limiter"
        assert len(res.spec.acceptance_criteria) >= 1
        assert res.spec.spec_hash is not None

        # 2. Stage 2: Planning & Risk Analysis
        assert len(res.plan.tasks) >= 1
        assert len(res.plan.risks) >= 1
        assert len(res.plan.impacted_files) >= 1

        # 3. Stage 3: Checkpoint #1 Pre-Implementation
        assert res.checkpoint_1.status == ApprovalStatus.APPROVED
        assert res.checkpoint_1.reviewer == "CI Lead"
        assert res.checkpoint_1.signature != ""

        # 4. Stage 4: Code Synthesis
        assert len(res.implementation.changes) >= 1
        assert (sandbox_dir / "src" / "models" / "feature.py").is_file()

        # 5. Stage 5: Test Generation & Traceability
        assert (sandbox_dir / "tests" / "test_acceptance.py").is_file()
        assert (sandbox_dir / "tests" / "conftest.py").is_file()

        # 6. Stage 6: Deterministic Quality Verification Gates
        assert res.quality_results.all_passed is True
        assert len(res.quality_results.gates) == 6
        for gate in res.quality_results.gates:
            assert gate.passed is True

        # 7. Stage 7: Checkpoint #2 Pre-Merge & Attestations
        assert res.checkpoint_2.status == ApprovalStatus.APPROVED
        assert res.checkpoint_2.signature != ""

        # Artifacts verification
        assert (artifacts_dir / f"audit_record_{res.audit_record.run_id}.json").is_file()
        assert (artifacts_dir / "provenance.json").is_file()
        assert (artifacts_dir / "audit_report.md").is_file()
        assert (artifacts_dir / "dashboard.html").is_file()

        # In-Toto SLSA statement structure
        prov_data = json.loads((artifacts_dir / "provenance.json").read_text(encoding="utf-8"))
        assert prov_data["_type"] == "https://in-toto.io/Statement/v0.1"
        assert prov_data["predicateType"] == "https://slsa.dev/provenance/v0.2"

    def test_e2e_markdown_spec_run(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = repo_root / "examples" / "specs" / "rate_limiter.md"
        sandbox_dir = tmp_path / "sandbox_md"
        artifacts_dir = tmp_path / "artifacts_md"

        orchestrator = PipelineOrchestrator(provider_type="mock")
        res = orchestrator.run_pipeline(
            spec_path_or_content=spec_file,
            sandbox_dir=sandbox_dir,
            artifacts_dir=artifacts_dir,
            auto_approve=True,
            reviewer="Release Bot",
        )

        assert res.spec.title == "Rate Limiter Service"
        assert res.quality_results.all_passed is True
        assert (artifacts_dir / "dashboard.html").is_file()

    def test_e2e_json_spec_run(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = repo_root / "examples" / "specs" / "audit_logger_service.json"
        sandbox_dir = tmp_path / "sandbox_json"
        artifacts_dir = tmp_path / "artifacts_json"

        orchestrator = PipelineOrchestrator(provider_type="mock")
        res = orchestrator.run_pipeline(
            spec_path_or_content=spec_file,
            sandbox_dir=sandbox_dir,
            artifacts_dir=artifacts_dir,
            auto_approve=True,
            reviewer="Security Lead",
        )

        assert res.spec.title == "Audit Logger Service"
        assert res.quality_results.all_passed is True
        assert (artifacts_dir / "audit_report.md").is_file()


# ──────────────────────────────────────────────────────────────────────────────
# 2.  CLI Subcommand Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPipelineCLI:
    def test_cli_validate_valid_spec(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = str(repo_root / "examples" / "specs" / "token_bucket_limiter.yaml")

        result = runner.invoke(app, ["validate", spec_file])
        assert result.exit_code == 0
        assert "All 6 mandatory specification sections valid" in result.output

    def test_cli_validate_nonexistent_file(self) -> None:
        result = runner.invoke(app, ["validate", "nonexistent_spec.yaml"])
        assert result.exit_code != 0

    def test_cli_plan_command(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = str(repo_root / "examples" / "specs" / "token_bucket_limiter.yaml")
        plan_out = str(tmp_path / "plan.json")

        result = runner.invoke(app, ["plan", spec_file, "--provider", "mock", "--output", plan_out])
        assert result.exit_code == 0
        assert "Technical Implementation Plan" in result.output
        assert Path(plan_out).is_file()

    def test_cli_run_command(self, tmp_path: Path) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = str(repo_root / "examples" / "specs" / "token_bucket_limiter.yaml")
        sandbox_dir = str(tmp_path / "cli_sandbox")
        artifacts_dir = str(tmp_path / "cli_artifacts")

        result = runner.invoke(
            app,
            [
                "run",
                spec_file,
                "--sandbox",
                sandbox_dir,
                "--artifacts",
                artifacts_dir,
                "--provider",
                "mock",
                "--auto-approve",
                "--reviewer",
                "CLI Test Runner",
            ],
        )

        assert result.exit_code == 0
        assert "PIPELINE RUN COMPLETED SUCCESSFULLY" in result.output
        assert (Path(artifacts_dir) / "dashboard.html").is_file()

    def test_cli_quality_check_command(self, tmp_path: Path) -> None:
        # 1. Setup a valid sandbox
        repo_root = Path(__file__).resolve().parent.parent
        spec_file = repo_root / "examples" / "specs" / "token_bucket_limiter.yaml"
        sandbox_dir = tmp_path / "qc_sandbox"

        orchestrator = PipelineOrchestrator(provider_type="mock")
        orchestrator.run_pipeline(
            spec_path_or_content=spec_file,
            sandbox_dir=sandbox_dir,
            auto_approve=True,
        )

        # 2. Run quality-check CLI command
        result = runner.invoke(app, ["quality-check", "--sandbox", str(sandbox_dir)])
        assert result.exit_code == 0
        assert "All quality gates passed cleanly" in result.output
