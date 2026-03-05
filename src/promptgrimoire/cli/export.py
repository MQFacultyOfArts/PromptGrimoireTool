"""Export log inspection commands."""

import re
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

export_app = typer.Typer(help="Export log inspection.")


def _find_export_dir(user_id: str | None) -> Path:
    """Find the export directory for a user or most recent."""
    tmp_dir = Path(tempfile.gettempdir())

    if user_id:
        export_dir = tmp_dir / f"promptgrimoire_export_{user_id}"
        if not export_dir.exists():
            console.print(f"[red]Error:[/] Export directory not found: {export_dir}")
            sys.exit(1)
        return export_dir

    export_dirs = list(tmp_dir.glob("promptgrimoire_export_*"))
    if not export_dirs:
        console.print("[red]Error:[/] No export directories found in temp folder")
        console.print(f"[dim]Searched in: {tmp_dir}[/]")
        sys.exit(1)

    return max(export_dirs, key=lambda p: p.stat().st_mtime)


def _show_error_context(log_file: Path, tex_file: Path) -> None:
    """Show LaTeX error with context from both log and tex file."""
    log_content = log_file.read_text()
    tex_lines = tex_file.read_text().splitlines()

    # Find error line number from log (pattern: "l.123")
    error_line_match = re.search(r"^l\.(\d+)", log_content, re.MULTILINE)
    error_line = int(error_line_match.group(1)) if error_line_match else None

    # Show last part of log (where errors appear)
    console.print("\n[bold red]LaTeX Error (last 100 lines of log):[/]")
    for line in log_content.splitlines()[-100:]:
        if line.startswith("!") or "Error" in line:
            console.print(f"[red]{line}[/]")
        elif line.startswith("l."):
            console.print(f"[yellow]{line}[/]")
        else:
            console.print(line)

    # Show tex context around error line
    if error_line:
        console.print(f"\n[bold yellow]TeX Source around line {error_line}:[/]")
        start = max(0, error_line - 15)
        end = min(len(tex_lines), error_line + 10)
        context = "\n".join(tex_lines[start:end])
        console.print(
            Syntax(
                context,
                "latex",
                line_numbers=True,
                start_line=start + 1,
                highlight_lines={error_line},
            )
        )
    else:
        console.print("\n[dim]Could not find error line number in log[/]")


@export_app.command("log")
def log(
    user_id: Annotated[
        str | None,
        typer.Argument(help="User ID (default: most recent export)"),
    ] = None,
    tex: Annotated[
        bool,
        typer.Option("--tex", help="Show .tex source instead of log"),
    ] = False,
    both: Annotated[
        bool,
        typer.Option("--both", help="Show error context from log and tex"),
    ] = False,
) -> None:
    """Show the most recent PDF export LaTeX log."""
    export_dir = _find_export_dir(user_id)
    log_file = export_dir / "annotated_document.log"
    tex_file = export_dir / "annotated_document.tex"

    console.print(
        Panel(
            f"[bold]Export Directory:[/] {export_dir}\n"
            f"[bold]TeX Source:[/] {tex_file}\n"
            f"[bold]LaTeX Log:[/] {log_file}",
            title="PDF Export Debug Files",
            border_style="blue",
        )
    )

    if both:
        if not tex_file.exists() or not log_file.exists():
            console.print("[red]Error:[/] Missing .tex or .log file")
            sys.exit(1)
        _show_error_context(log_file, tex_file)
    elif tex:
        if not tex_file.exists():
            console.print(f"[red]Error:[/] TeX file not found: {tex_file}")
            sys.exit(1)
        with console.pager():
            console.print(
                Syntax(
                    tex_file.read_text(),
                    "latex",
                    line_numbers=True,
                )
            )
    else:
        if not log_file.exists():
            console.print(f"[red]Error:[/] Log file not found: {log_file}")
            sys.exit(1)
        with console.pager():
            console.print(log_file.read_text())
