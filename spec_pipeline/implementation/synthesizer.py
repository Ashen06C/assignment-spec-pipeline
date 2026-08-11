"""AI-assisted code synthesizer orchestrating generation, governance checks, and safe patching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from spec_pipeline.core.config import load_settings

if TYPE_CHECKING:
    from pathlib import Path
from spec_pipeline.core.models import (
    FeatureSpec,
    FileChange,
    ImplementationOutput,
    ImplementationPlan,
)
from spec_pipeline.governance.sandbox_policy import SandboxPolicyEnforcer
from spec_pipeline.implementation.patch_engine import PatchEngine
from spec_pipeline.llm import BaseLLMProvider, LLMConfig, get_llm_provider
from spec_pipeline.llm.json_util import parse_llm_json
from spec_pipeline.llm.prompt_templates import (
    CODE_SYNTHESIS_SYSTEM_PROMPT,
    build_code_synthesis_prompt,
)


class CodeSynthesizer:
    """Orchestrates AI-driven code generation with strict sandbox governance."""

    def __init__(
        self,
        llm: BaseLLMProvider | None = None,
        policy_enforcer: SandboxPolicyEnforcer | None = None,
        patch_engine: PatchEngine | None = None,
    ) -> None:
        if llm is None:
            settings = load_settings()
            llm_config = LLMConfig(
                provider=settings.llm_provider,
                model=settings.llm_model,
                api_key=settings.active_api_key,
            )
            self.llm = get_llm_provider(llm_config)
        else:
            self.llm = llm

        self.policy_enforcer = policy_enforcer or SandboxPolicyEnforcer()
        self.patch_engine = patch_engine or PatchEngine()

    def synthesize(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        sandbox_root: str | Path | None = None,
    ) -> ImplementationOutput:
        """Generate code changes from *spec* and *plan*, enforcing blast radius boundaries.

        Parameters
        ----------
        spec:
            The approved feature specification.
        plan:
            The approved technical implementation plan.
        sandbox_root:
            Optional sandbox directory to immediately apply and verify file patches.

        Returns
        -------
        ImplementationOutput
            The synthesized changes, diff summaries, and overall metadata.

        Raises
        ------
        SandboxPolicyViolationError
            If generated changes attempt path traversal or exceed approved blast radius.
        """
        spec_dict = spec.model_dump(mode="json")
        plan_dict = plan.model_dump(mode="json")

        prompt = build_code_synthesis_prompt(spec_dict, plan_dict)
        raw_response, _usage = self.llm.generate(
            prompt,
            system_prompt=CODE_SYNTHESIS_SYSTEM_PROMPT,
        )

        output_data = parse_llm_json(raw_response)
        if not isinstance(output_data, dict):
            raise ValueError("Expected JSON object from LLM code synthesis response")

        raw_changes = output_data.get("changes", [])
        changes: list[FileChange] = [
            FileChange(**c) for c in raw_changes if isinstance(c, dict)
        ]

        # 1. Strict Sandbox Policy Verification
        self.policy_enforcer.validate_changes(
            changes,
            allowed_files=plan.impacted_files,
        )

        # 2. Apply Patches to Sandbox if requested
        if sandbox_root is not None:
            changes = self.patch_engine.apply_changes(changes, sandbox_root)

        change_summary = output_data.get(
            "change_summary",
            f"Generated {len(changes)} code changes for '{spec.title}'.",
        )

        return ImplementationOutput(
            plan_id=plan.plan_id,
            changes=changes,
            change_summary=change_summary,
        )
