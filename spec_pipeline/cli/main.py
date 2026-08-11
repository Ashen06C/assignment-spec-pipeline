"""Typer CLI interface for the AI-native spec-driven development pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from spec_pipeline.orchestrator import PipelineOrchestrator
from spec_pipeline.quality_gates.runner import QualityGateRunner
from spec_pipeline.spec_intake.parser import SpecParser
from spec_pipeline.spec_intake.validator import SpecValidator

app = typer.Typer(
    name="spec-pipeline",
    help="AI-Native Spec-Driven Development Pipeline CLI.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def validate(
    spec_path: Annotated[
        Path,
        typer.Argument(
            help="Path to specification file (.md, .yaml, .yml, .json)",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
) -> None:
    """Validate a specification file against the mandatory 6-section schema standard."""
    parser = SpecParser()
    validator = SpecValidator()

    try:
        spec = parser.parse_file(spec_path)
        errors = validator.validate(spec)
    except Exception as exc:
        console.print(f"[bold red]Intake Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    if errors:
        console.print(
            Panel(
                f"[bold red]Specification Validation Failed ({len(errors)} error(s)):[/]\n\n"
                + "\n".join(f"• {e}" for e in errors),
                title="Validation Errors",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    table = Table(title=f"Specification Validated: {spec.title}", border_style="green")
    table.add_column("Section", style="cyan", width=25)
    table.add_column("Count / Details", style="white")

    table.add_row("Feature Objective", spec.objective[:60] + "...")
    table.add_row("User Stories", f"{len(spec.user_stories)} item(s)")
    table.add_row("Business Rules", f"{len(spec.business_rules)} rule(s)")
    table.add_row("Acceptance Criteria", f"{len(spec.acceptance_criteria)} scenario(s)")
    table.add_row("Non-Functional Reqs", f"{len(spec.non_functional_requirements)} requirement(s)")
    table.add_row("Out-of-Scope Items", f"{len(spec.out_of_scope)} item(s)")
    table.add_row("SHA-256 Fingerprint", f"[dim]{spec.spec_hash}[/]")

    console.print(table)
    console.print("[bold green][PASSED] All 6 mandatory specification sections valid.[/]\n")


@app.command()
def plan(
    spec_path: Annotated[
        Path,
        typer.Argument(
            help="Path to specification file",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="LLM Provider: mock | gemini | openai"),
    ] = "mock",
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model name override"),
    ] = None,
    output_file: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional path to save plan JSON"),
    ] = None,
) -> None:
    """Generate technical implementation plan, task DAG, blast radius, and risk mitigations."""
    orchestrator = PipelineOrchestrator(
        provider_type=provider,
        model_name=model,
        console=console,
    )

    try:
        spec, plan_obj, _ = orchestrator.stage_plan(spec_path)
    except Exception as exc:
        console.print(f"[bold red]Planning Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"[bold green]Technical Implementation Plan for '{spec.title}'[/]\n"
            f"[white]{plan_obj.technical_summary}[/]",
            border_style="cyan",
        )
    )

    # Tasks table
    task_table = Table(title="Ordered Implementation Tasks (DAG)", border_style="green")
    task_table.add_column("Task ID", style="cyan")
    task_table.add_column("Title", style="white")
    task_table.add_column("Priority", style="yellow")
    task_table.add_column("Effort", style="magenta")
    task_table.add_column("Target Files", style="dim")

    for task in plan_obj.tasks:
        files = ", ".join(task.target_files) if task.target_files else "—"
        task_table.add_row(
            task.task_id,
            task.title,
            task.priority.upper(),
            task.estimated_effort or "—",
            files,
        )
    console.print(task_table)

    # Risks table
    if plan_obj.risks:
        risk_table = Table(title="Evaluated Risks & Mitigations", border_style="yellow")
        risk_table.add_column("Risk ID", style="red")
        risk_table.add_column("Category", style="cyan")
        risk_table.add_column("Description", style="white")
        risk_table.add_column("Mitigation", style="green")

        for risk in plan_obj.risks:
            risk_table.add_row(
                risk.risk_id,
                risk.category,
                risk.description,
                risk.mitigation,
            )
        console.print(risk_table)

    if output_file:
        import json

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(plan_obj.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        console.print(f"\n[green]Plan saved to:[/] {output_file}")


@app.command()
def run(
    spec_path: Annotated[
        Path,
        typer.Argument(
            help="Path to specification file",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    sandbox: Annotated[
        Path,
        typer.Option("--sandbox", "-s", help="Target sandbox directory for synthesis"),
    ] = Path("./sandbox"),
    artifacts: Annotated[
        Path,
        typer.Option("--artifacts", "-a", help="Artifacts directory for audit trail & reports"),
    ] = Path("./artifacts"),
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="LLM Provider: mock | gemini | openai"),
    ] = "mock",
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Model name override"),
    ] = None,
    auto_approve: Annotated[
        bool,
        typer.Option("--auto-approve", help="Bypass interactive approval checkpoints for CI"),
    ] = False,
    reviewer: Annotated[
        str,
        typer.Option("--reviewer", "-r", help="Reviewer identity name"),
    ] = "Lead Engineer",
) -> None:
    """Execute complete 7-stage end-to-end spec-driven development pipeline."""
    orchestrator = PipelineOrchestrator(
        provider_type=provider,
        model_name=model,
        console=console,
    )

    console.print(
        Panel.fit(
            f"[bold blue]Spec-Driven Pipeline Execution[/]\n"
            f"Spec: [white]{spec_path}[/]\n"
            f"Provider: [yellow]{provider}[/]"
            + (f" ({model})" if model else "")
            + f"\nSandbox: [cyan]{sandbox}[/]\nArtifacts: [magenta]{artifacts}[/]",
            border_style="blue",
        )
    )

    try:
        res = orchestrator.run_pipeline(
            spec_path_or_content=spec_path,
            sandbox_dir=sandbox,
            artifacts_dir=artifacts,
            auto_approve=auto_approve,
            reviewer=reviewer,
        )
    except Exception as exc:
        console.print(f"\n[bold red]Pipeline Execution Halted:[/] {exc}")
        raise typer.Exit(code=1) from exc

    status_color = "green" if res.quality_results.all_passed else "red"
    summary_text = (
        f"[bold {status_color}]PIPELINE RUN COMPLETED SUCCESSFULLY[/]\n\n"
        f"• [white]Run ID:[/] {res.audit_record.run_id}\n"
        f"• [white]Quality Gates:[/] {len([g for g in res.quality_results.gates if g.passed])}/"
        f"{len(res.quality_results.gates)} passed\n"
        f"• [white]Code Diffs:[/] {len(res.implementation.changes)} file(s) generated\n"
        f"• [white]Tests Generated:[/] {len(res.test_generation.tests)} test scenario(s)\n"
        f"• [white]Checkpoint #1 Sig:[/] [dim]{res.checkpoint_1.signature[:16]}...[/]\n"
        f"• [white]Checkpoint #2 Sig:[/] [dim]{res.checkpoint_2.signature[:16]}...[/]\n"
        f"• [white]SLSA Provenance:[/] {artifacts / 'provenance.json'}\n"
        f"• [white]HTML Dashboard:[/] {artifacts / 'dashboard.html'}"
    )

    console.print()
    console.print(Panel(summary_text, title="Execution Summary", border_style=status_color))


@app.command(name="quality-check")
def quality_check(
    sandbox: Annotated[
        Path,
        typer.Option("--sandbox", "-s", help="Sandbox root directory to verify"),
    ] = Path("./sandbox"),
) -> None:
    """Execute the 6 deterministic quality verification gates on an existing sandbox."""
    if not sandbox.is_dir():
        console.print(f"[bold red]Sandbox directory does not exist:[/] {sandbox}")
        raise typer.Exit(code=1)

    runner = QualityGateRunner()
    console.print(f"[bold cyan]Running quality verification gates on {sandbox}...[/]\n")

    table = Table(title="Quality Gate Verification Results", border_style="cyan")
    table.add_column("Gate Name", style="white", width=20)
    table.add_column("Result", width=12)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Details", style="dim")

    # Run individual gates
    all_passed = True
    for gate in runner.gates:
        res = gate.execute(sandbox_root=sandbox)
        if not res.passed:
            all_passed = False
        status = "[bold green]PASSED[/]" if res.passed else "[bold red]FAILED[/]"
        dur = f"{res.duration_seconds:.3f}s" if res.duration_seconds is not None else "—"
        table.add_row(res.gate_name, status, dur, res.details)

    console.print(table)
    if not all_passed:
        console.print("[bold red]One or more quality gates failed.[/]")
        raise typer.Exit(code=1)

    console.print("[bold green]All quality gates passed cleanly.[/]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
