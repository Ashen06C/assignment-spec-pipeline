"""Two-stage human governance approval gate with Rich UI and HMAC-SHA256 signatures."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from spec_pipeline.core.exceptions import ApprovalRejectedError
from spec_pipeline.core.models import ApprovalDecision, ApprovalStatus

if TYPE_CHECKING:
    from spec_pipeline.core.models import (
        FeatureSpec,
        ImplementationOutput,
        ImplementationPlan,
        QualityGateSuiteResult,
    )

DEFAULT_SIGNING_SECRET = "governance-hmac-key"


class HumanApprovalGate:
    """Manages two-stage human approval checkpoints with cryptographic auditability."""

    CHECKPOINT_PRE_IMPLEMENTATION = "pre-implementation"
    CHECKPOINT_PRE_MERGE = "pre-merge"

    def __init__(
        self,
        signing_secret: str | None = None,
        console: Console | None = None,
    ) -> None:
        self.signing_secret: str = (
            signing_secret
            or os.getenv("GOVERNANCE_SIGNING_SECRET")
            or DEFAULT_SIGNING_SECRET
        )
        self.console = console or Console()

    # ── Checkpoint 1: Pre-Implementation ──────────────────────────────────── #

    def request_pre_implementation_approval(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        auto_approve: bool = False,
        reviewer: str = "Lead Engineer",
        comments: str = "",
    ) -> ApprovalDecision:
        """Checkpoint #1: Review technical design, task DAG, blast radius, and risks."""
        if not auto_approve:
            self._render_pre_implementation_dashboard(spec, plan)
            is_approved = Confirm.ask(
                "[bold cyan]Checkpoint #1[/]: Approve design for implementation?",
                default=True,
                console=self.console,
            )
            if not is_approved:
                reason = Prompt.ask(
                    "[bold red]Rejection reason[/]",
                    default="Technical plan rejected by reviewer",
                    console=self.console,
                )
                self._record_decision(
                    checkpoint=self.CHECKPOINT_PRE_IMPLEMENTATION,
                    status=ApprovalStatus.REJECTED,
                    reviewer=reviewer,
                    comments=reason,
                )
                raise ApprovalRejectedError(self.CHECKPOINT_PRE_IMPLEMENTATION, reason)

        return self._record_decision(
            checkpoint=self.CHECKPOINT_PRE_IMPLEMENTATION,
            status=ApprovalStatus.APPROVED,
            reviewer=reviewer,
            comments=comments or "Pre-implementation design and blast radius approved.",
            payload_hash=spec.spec_hash or str(plan.plan_id),
        )

    # ── Checkpoint 2: Pre-Merge / Pre-Deployment ──────────────────────────── #

    def request_pre_merge_approval(
        self,
        spec: FeatureSpec,
        plan: ImplementationPlan,
        implementation: ImplementationOutput,
        quality_suite: QualityGateSuiteResult,
        auto_approve: bool = False,
        reviewer: str = "Release Lead",
        comments: str = "",
    ) -> ApprovalDecision:
        """Checkpoint #2: Review 100% quality gate evidence and synthesized file diffs."""
        if not auto_approve:
            self._render_pre_merge_dashboard(spec, implementation, quality_suite)
            is_approved = Confirm.ask(
                "[bold cyan]Checkpoint #2[/]: Approve quality evidence for merge?",
                default=True,
                console=self.console,
            )
            if not is_approved:
                reason = Prompt.ask(
                    "[bold red]Rejection reason[/]",
                    default="Release evidence rejected by reviewer",
                    console=self.console,
                )
                self._record_decision(
                    checkpoint=self.CHECKPOINT_PRE_MERGE,
                    status=ApprovalStatus.REJECTED,
                    reviewer=reviewer,
                    comments=reason,
                )
                raise ApprovalRejectedError(self.CHECKPOINT_PRE_MERGE, reason)

        return self._record_decision(
            checkpoint=self.CHECKPOINT_PRE_MERGE,
            status=ApprovalStatus.APPROVED,
            reviewer=reviewer,
            comments=comments or "All 6 quality gates passed; diffs and tests approved for merge.",
            payload_hash=str(plan.plan_id),
        )

    # ── Cryptographic Signature Helpers ───────────────────────────────────── #

    def generate_signature(
        self,
        checkpoint: str,
        status: str,
        reviewer: str,
        timestamp_iso: str,
        payload_hash: str = "",
    ) -> str:
        """Compute an immutable HMAC-SHA256 cryptographic signature token."""
        message = f"{checkpoint}:{status}:{reviewer}:{timestamp_iso}:{payload_hash}".encode()
        key = (self.signing_secret or DEFAULT_SIGNING_SECRET).encode()
        return hmac.new(
            key,
            message,
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(
        self,
        decision: ApprovalDecision,
        payload_hash: str = "",
    ) -> bool:
        """Verify the authenticity and integrity of an ApprovalDecision signature."""
        if not decision.decided_at or not decision.signature:
            return False

        timestamp_iso = decision.decided_at.isoformat()
        expected = self.generate_signature(
            checkpoint=decision.checkpoint,
            status=decision.status.value,
            reviewer=decision.reviewer,
            timestamp_iso=timestamp_iso,
            payload_hash=payload_hash,
        )
        return hmac.compare_digest(decision.signature, expected)

    def _record_decision(
        self,
        checkpoint: str,
        status: ApprovalStatus,
        reviewer: str,
        comments: str,
        payload_hash: str = "",
    ) -> ApprovalDecision:
        now = datetime.now(UTC)
        sig = self.generate_signature(
            checkpoint=checkpoint,
            status=status.value,
            reviewer=reviewer,
            timestamp_iso=now.isoformat(),
            payload_hash=payload_hash,
        )
        return ApprovalDecision(
            checkpoint=checkpoint,
            status=status,
            reviewer=reviewer,
            comments=comments,
            signature=sig,
            decided_at=now,
        )

    # ── Rich UI Presentation Dashboards ───────────────────────────────────── #

    def _render_pre_implementation_dashboard(
        self, spec: FeatureSpec, plan: ImplementationPlan
    ) -> None:
        self.console.print()
        self.console.print(
            Panel.fit(
                f"[bold green]GOVERNANCE CHECKPOINT #1: PRE-IMPLEMENTATION[/]\n"
                f"[white]Feature:[/] {spec.title} (v{spec.version})\n"
                f"[white]Objective:[/] {spec.objective}",
                border_style="cyan",
            )
        )

        # 1. Architecture Decisions
        if plan.architecture_decisions:
            adr_table = Table(title="Architecture Decisions (ADRs)", border_style="blue")
            adr_table.add_column("Decision", style="white")
            for adr in plan.architecture_decisions:
                adr_table.add_row(adr)
            self.console.print(adr_table)

        # 2. Tasks & Target Files
        task_table = Table(title="Ordered Implementation Tasks (DAG)", border_style="green")
        task_table.add_column("Task ID", style="cyan", width=12)
        task_table.add_column("Title", style="white")
        task_table.add_column("Priority", style="yellow")
        task_table.add_column("Est.", style="magenta")
        task_table.add_column("Target Files", style="dim")

        for task in plan.tasks:
            files_str = ", ".join(task.target_files) if task.target_files else "—"
            task_table.add_row(
                task.task_id,
                task.title,
                task.priority.upper(),
                task.estimated_effort or "—",
                files_str,
            )
        self.console.print(task_table)

        # 3. Risks & Mitigations
        if plan.risks:
            risk_table = Table(title="Evaluated Risks & Mitigations", border_style="yellow")
            risk_table.add_column("Risk ID", style="red", width=12)
            risk_table.add_column("Category", style="cyan")
            risk_table.add_column("Description", style="white")
            risk_table.add_column("Mitigation", style="green")

            for risk in plan.risks:
                risk_table.add_row(
                    risk.risk_id,
                    risk.category,
                    risk.description,
                    risk.mitigation,
                )
            self.console.print(risk_table)
        self.console.print()

    def _render_pre_merge_dashboard(
        self,
        spec: FeatureSpec,
        implementation: ImplementationOutput,
        quality_suite: QualityGateSuiteResult,
    ) -> None:
        self.console.print()
        status_color = "green" if quality_suite.all_passed else "red"
        gate_summary = "ALL 6 GATES PASSED" if quality_suite.all_passed else "GATES FAILED"
        self.console.print(
            Panel.fit(
                f"[bold {status_color}]GOVERNANCE CHECKPOINT #2: PRE-MERGE / DEPLOYMENT[/]\n"
                f"[white]Feature:[/] {spec.title}\n"
                f"[white]Quality Gate Status:[/] [bold {status_color}]{gate_summary}[/]",
                border_style=status_color,
            )
        )

        # 1. Quality Gate Evidence Table
        gate_table = Table(title="Deterministic Quality Gate Evidence", border_style="cyan")
        gate_table.add_column("Gate", style="white", width=18)
        gate_table.add_column("Result", width=12)
        gate_table.add_column("Duration", justify="right", width=10)
        gate_table.add_column("Details", style="dim")

        for gate in quality_suite.gates:
            status = "[bold green]PASSED[/]" if gate.passed else "[bold red]FAILED[/]"
            dur = f"{gate.duration_seconds:.3f}s" if gate.duration_seconds is not None else "—"
            gate_table.add_row(gate.gate_name, status, dur, gate.details)
        self.console.print(gate_table)

        # 2. File Changes & Diff Summaries
        diff_table = Table(title="Synthesized File Modifications", border_style="magenta")
        diff_table.add_column("Path", style="cyan")
        diff_table.add_column("Action", style="yellow")
        diff_table.add_column("Diff Summary", style="white")

        for change in implementation.changes:
            summary = change.diff_summary or "File modified"
            diff_table.add_row(change.path, change.action.upper(), summary.splitlines()[0])
        self.console.print(diff_table)
        self.console.print()
