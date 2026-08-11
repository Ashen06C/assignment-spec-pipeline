"""CLI entry point (placeholder — will be expanded in later tasks)."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="spec-pipeline",
    help="AI-native, spec-driven development pipeline CLI.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the pipeline version."""
    typer.echo("spec-pipeline v0.1.0")


if __name__ == "__main__":
    app()
