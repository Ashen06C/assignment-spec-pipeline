"""One-click executable demo script for the Spec-Driven Pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from spec_pipeline.orchestrator import PipelineOrchestrator


def run_demo() -> None:
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]AI-Native Spec-Driven Development Pipeline[/]\n"
            "[white]Autonomous End-to-End Lifecycle Execution Demo[/]",
            border_style="cyan",
        )
    )

    repo_root = Path(__file__).resolve().parent
    spec_path = repo_root / "examples" / "specs" / "token_bucket_limiter.yaml"
    sandbox_dir = repo_root / "sandbox" / "demo_sandbox"
    artifacts_dir = repo_root / "artifacts" / "demo_run"

    if not spec_path.is_file():
        console.print(f"[bold red]Example spec not found at {spec_path}[/]")
        sys.exit(1)

    console.print(f"[bold green]1. Loaded Specification:[/] [white]{spec_path.name}[/]")
    console.print(f"[bold green]2. Target Sandbox:[/] [white]{sandbox_dir}[/]")
    console.print(f"[bold green]3. Target Artifacts:[/] [white]{artifacts_dir}[/]\n")

    orchestrator = PipelineOrchestrator(
        provider_type="mock",
        console=console,
    )

    console.print("[bold cyan]Executing full 7-stage lifecycle...[/]\n")

    result = orchestrator.run_pipeline(
        spec_path_or_content=spec_path,
        sandbox_dir=sandbox_dir,
        artifacts_dir=artifacts_dir,
        auto_approve=True,
        reviewer="Architect",
    )

    status_color = "green" if result.quality_results.all_passed else "red"
    console.print()
    console.print(
        Panel(
            f"[bold {status_color}]DEMO RUN COMPLETE: ALL GATES & ATTESTATIONS GENERATED[/]\n\n"
            f"• [white]Feature Objective:[/] {result.spec.objective}\n"
            f"• [white]Tasks Decomposed:[/] {len(result.plan.tasks)} task(s)\n"
            f"• [white]Evaluated Risks:[/] {len(result.plan.risks)} identified with mitigations\n"
            f"• [white]Files Synthesized:[/] {len(result.implementation.changes)} file(s)\n"
            f"• [white]Automated Tests:[/] {len(result.test_generation.tests)} test scenario(s)\n"
            f"• [white]Quality Gates:[/] 6/6 deterministic gates executed "
            f"({'PASSED' if result.quality_results.all_passed else 'FAILED'})\n"
            f"• [white]HMAC Signatures:[/] CP1: {result.checkpoint_1.signature[:10]}... | "
            f"CP2: {result.checkpoint_2.signature[:10]}...\n"
            f"• [white]SLSA Provenance:[/] [cyan]{artifacts_dir / 'provenance.json'}[/]\n"
            f"• [white]HTML Dashboard:[/] [cyan]{artifacts_dir / 'dashboard.html'}[/]\n"
            f"• [white]Markdown Report:[/] [cyan]{artifacts_dir / 'audit_report.md'}[/]",
            title="Demo Result Summary",
            border_style=status_color,
        )
    )


if __name__ == "__main__":
    run_demo()
