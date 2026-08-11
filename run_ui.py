"""One-click launcher for the AI-Native Spec-Driven Pipeline Web Studio."""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser

from rich.console import Console
from rich.panel import Panel

from spec_pipeline.web.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the AI-Native Spec-Driven Pipeline Web Studio"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not automatically open browser"
    )
    args = parser.parse_args()

    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]AI-Native Spec-Driven Pipeline Web Studio[/]\n"
            f"Studio URL: [bold underline green]http://{args.host}:{args.port}/[/]\n\n"
            "[dim]Features: Multi-format Spec Intake, Live 6-Section Schema Validation,\n"
            "Task DAG Planner, Isolated Code Synthesis, 6 Deterministic Quality Gates,\n"
            "Two-Stage Human Governance Checkpoints, SLSA v0.2 In-Toto Provenance[/]",
            border_style="cyan",
            title="Studio Launcher",
        )
    )

    try:
        server = create_server(host=args.host, port=args.port)
    except OSError as err:
        console.print(f"[bold red]Failed to bind to {args.host}:{args.port}: {err}[/]")
        sys.exit(1)

    url = f"http://{args.host}:{args.port}/"

    # Open browser in separate thread
    if not args.no_browser:
        def _open_browser() -> None:
            time.sleep(0.5)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    console.print(f"[bold green]Serving Web Studio at {url}[/]")
    console.print("[dim]Press Ctrl+C to stop server.[/]\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Stopping Web Studio server...[/]")
    finally:
        server.server_close()
        console.print("[green]Server stopped cleanly.[/]")


if __name__ == "__main__":
    main()
