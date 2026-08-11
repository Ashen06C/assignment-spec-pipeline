"""Tests for sandbox policy enforcement, blast radius containment, and atomic patching."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from spec_pipeline.core.exceptions import SandboxPolicyViolationError
from spec_pipeline.core.models import (
    AcceptanceCriterion,
    BusinessRule,
    DecomposedTask,
    FeatureSpec,
    FileChange,
    ImplementationPlan,
    NonFunctionalRequirement,
    UserStory,
)
from spec_pipeline.governance.sandbox_policy import SandboxPolicyEnforcer
from spec_pipeline.implementation.patch_engine import PatchEngine
from spec_pipeline.implementation.synthesizer import CodeSynthesizer
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, MockProvider, TokenUsage


@pytest.fixture
def policy() -> SandboxPolicyEnforcer:
    return SandboxPolicyEnforcer()


@pytest.fixture
def patch_engine() -> PatchEngine:
    return PatchEngine()


def _create_test_spec(title: str = "Test Feature") -> FeatureSpec:
    """Helper to construct a fully valid FeatureSpec with all 6 mandatory sections."""
    return FeatureSpec(
        title=title,
        objective=f"Objective for {title}",
        user_stories=[UserStory(as_a="user", i_want="action", so_that="benefit")],
        business_rules=[BusinessRule(rule_id="BR-001", description="Valid rule")],
        acceptance_criteria=[
            AcceptanceCriterion(
                criterion_id="AC-001",
                title="Criterion title",
                given="given",
                when="when",
                then="then",
            )
        ],
        non_functional_requirements=[
            NonFunctionalRequirement(category="performance", description="Fast")
        ],
        out_of_scope=["Out of scope item"],
    )


def _create_test_plan(impacted_files: list[str]) -> ImplementationPlan:
    """Construct a minimal plan for testing."""
    spec = _create_test_spec()
    return ImplementationPlan(
        spec_id=spec.spec_id,
        technical_summary="Summary",
        impacted_files=impacted_files,
        tasks=[
            DecomposedTask(
                task_id="TASK-001",
                title="T1",
                description="desc",
                target_files=impacted_files,
            )
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1.  Sandbox Policy Enforcer Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSandboxPolicyEnforcer:
    def test_allows_approved_files(self, policy: SandboxPolicyEnforcer) -> None:
        allowed = ["src/services/rate_limiter.py", "src/models/config.py"]
        assert policy.is_path_safe("src/services/rate_limiter.py", allowed)
        assert policy.is_path_safe("src/models/config.py", allowed)

    def test_allows_package_markers_in_approved_directories(
        self, policy: SandboxPolicyEnforcer
    ) -> None:
        allowed = ["src/services/rate_limiter.py"]
        assert policy.is_path_safe("src/services/__init__.py", allowed)

    def test_blocks_unapproved_files(self, policy: SandboxPolicyEnforcer) -> None:
        allowed = ["src/services/rate_limiter.py"]
        assert not policy.is_path_safe("src/services/other.py", allowed)
        assert not policy.is_path_safe("unauthorized/file.py", allowed)

    def test_blocks_path_traversal(self, policy: SandboxPolicyEnforcer) -> None:
        allowed = ["src/file.py"]
        traversal_attempts = [
            "../secret.txt",
            "src/../../etc/passwd",
            "..\\..\\Windows\\cmd.exe",
            "src/services/../../../root.py",
        ]
        for path in traversal_attempts:
            assert not policy.is_path_safe(path, allowed)
            violations = policy.check_violations(path, allowed)
            assert any("traversal" in v.lower() or "protected" in v.lower() for v in violations)

    def test_blocks_absolute_paths(self, policy: SandboxPolicyEnforcer) -> None:
        allowed = ["src/file.py"]
        abs_paths = [
            "/etc/passwd",
            "/var/log/app.log",
            "C:/secrets.json",
            "C:\\Windows\\System32\\calc.exe",
        ]
        for path in abs_paths:
            assert not policy.is_path_safe(path, allowed)
            violations = policy.check_violations(path, allowed)
            assert any("absolute" in v.lower() or "protected" in v.lower() for v in violations)

    def test_blocks_protected_files(self, policy: SandboxPolicyEnforcer) -> None:
        protected_files = [
            ".env",
            ".env.production",
            ".git/config",
            ".github/workflows/deploy.yml",
            ".ssh/id_rsa",
            "credentials.json",
            "secrets/api_keys.json",
        ]
        for path in protected_files:
            assert not policy.is_path_safe(path)
            violations = policy.check_violations(path)
            assert any("protected" in v.lower() for v in violations)

    def test_validate_changes_raises_on_violation(
        self, policy: SandboxPolicyEnforcer
    ) -> None:
        changes = [
            FileChange(path="src/approved.py", action="create", content="pass"),
            FileChange(path=".env", action="modify", content="SECRET=123"),
            FileChange(path="../outside.py", action="create", content="bad"),
        ]
        allowed = ["src/approved.py"]
        with pytest.raises(SandboxPolicyViolationError) as exc_info:
            policy.validate_changes(changes, allowed_files=allowed)

        error_msg = str(exc_info.value)
        assert ".env" in error_msg
        assert "../outside.py" in error_msg


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Patch Engine Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPatchEngine:
    def test_create_file_and_directories(
        self, patch_engine: PatchEngine, tmp_path: Path
    ) -> None:
        changes = [
            FileChange(
                path="src/models/user.py",
                action="create",
                content="class User:\n    pass\n",
            )
        ]
        applied = patch_engine.apply_changes(changes, tmp_path)
        target = tmp_path / "src" / "models" / "user.py"

        assert target.is_file()
        assert target.read_text(encoding="utf-8") == "class User:\n    pass\n"
        assert len(applied) == 1
        assert "Created src/models/user.py" in (applied[0].diff_summary or "")

    def test_modify_file_with_unified_diff(
        self, patch_engine: PatchEngine, tmp_path: Path
    ) -> None:
        target = tmp_path / "src" / "service.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def run():\n    return 1\n", encoding="utf-8")

        changes = [
            FileChange(
                path="src/service.py",
                action="modify",
                content="def run():\n    return 2\n",
            )
        ]
        applied = patch_engine.apply_changes(changes, tmp_path)

        assert target.read_text(encoding="utf-8") == "def run():\n    return 2\n"
        diff_summary = applied[0].diff_summary or ""
        assert "-    return 1" in diff_summary
        assert "+    return 2" in diff_summary

    def test_delete_file(self, patch_engine: PatchEngine, tmp_path: Path) -> None:
        target = tmp_path / "src" / "old.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# obsolete\n", encoding="utf-8")

        changes = [FileChange(path="src/old.py", action="delete")]
        applied = patch_engine.apply_changes(changes, tmp_path)

        assert not target.is_file()
        assert "Deleted src/old.py" in (applied[0].diff_summary or "")

    def test_atomic_rollback_on_failure(
        self, patch_engine: PatchEngine, tmp_path: Path
    ) -> None:
        # Pre-existing file
        existing_file = tmp_path / "src" / "stable.py"
        existing_file.parent.mkdir(parents=True, exist_ok=True)
        existing_file.write_text("STABLE = True\n", encoding="utf-8")

        changes = [
            # 1. Successful modification
            FileChange(
                path="src/stable.py",
                action="modify",
                content="STABLE = False\n",
            ),
            # 2. Successful creation
            FileChange(
                path="src/temp.py",
                action="create",
                content="TEMP = True\n",
            ),
            # 3. Illegal action causing failure
            FileChange(
                path="src/invalid.py",
                action="unsupported_action",
                content="FAIL",
            ),
        ]

        with pytest.raises(ValueError, match="Unknown change action"):
            patch_engine.apply_changes(changes, tmp_path)

        # Verify atomic rollback: stable.py restored, temp.py removed
        assert existing_file.read_text(encoding="utf-8") == "STABLE = True\n"
        assert not (tmp_path / "src" / "temp.py").is_file()


# ──────────────────────────────────────────────────────────────────────────────
# 3.  Code Synthesizer Integration Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCodeSynthesizer:
    def test_synthesizes_and_patches_successfully(self, tmp_path: Path) -> None:
        mock_llm = MockProvider(LLMConfig(provider="mock"))
        synthesizer = CodeSynthesizer(llm=mock_llm)

        spec = _create_test_spec("Feature X")
        plan = _create_test_plan(
            impacted_files=["src/models/feature.py", "src/services/feature_service.py"]
        )

        output = synthesizer.synthesize(spec, plan, sandbox_root=tmp_path)

        assert len(output.changes) == 2
        assert (tmp_path / "src" / "models" / "feature.py").is_file()
        assert (tmp_path / "src" / "services" / "feature_service.py").is_file()

    def test_rejects_synthesis_violating_blast_radius(self) -> None:
        class RogueProvider(BaseLLMProvider):
            def generate(
                self,
                prompt: str,
                *,
                system_prompt: str = "",
                temperature: float | None = None,
            ) -> tuple[str, TokenUsage]:
                import json

                rogue_payload = {
                    "changes": [
                        {
                            "path": ".env",
                            "action": "modify",
                            "content": "STOLEN_KEYS=1",
                            "diff_summary": "Malicious edit",
                        }
                    ],
                    "change_summary": "Rogue patch",
                }
                return json.dumps(rogue_payload), TokenUsage()

        synthesizer = CodeSynthesizer(llm=RogueProvider(LLMConfig(provider="mock")))
        spec = _create_test_spec("Safe Spec")
        plan = _create_test_plan(impacted_files=["src/models/feature.py"])

        with pytest.raises(SandboxPolicyViolationError) as exc_info:
            synthesizer.synthesize(spec, plan)

        assert ".env" in str(exc_info.value)
