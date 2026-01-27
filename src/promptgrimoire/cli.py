"""Command-line utilities for PromptGrimoire development.

Provides pytest wrappers with logging and timing for debugging test failures.
Also includes admin bootstrap commands.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
) -> None:
    """Run pytest with Rich formatting and logging."""
    start_time = datetime.now()
    user_args = sys.argv[1:]
    all_args = ["uv", "run", "pytest", *default_args, *user_args]
    command_str = " ".join(all_args[2:])

    # Header panel
    header_text = Text()
    header_text.append(f"{title}\n", style="bold")
    header_text.append(f"Started: {start_time.strftime('%H:%M:%S')}\n", style="dim")
    header_text.append(f"Command: {command_str}", style="cyan")
    console.print(Panel(header_text, border_style="blue"))

    # Plain text header for log file
    log_header = f"""{"=" * 60}
{title}
Started: {start_time.isoformat()}
Command: {command_str}
{"=" * 60}

"""

    with log_path.open("w") as log_file:
        log_file.write(log_header)
        log_file.flush()

        process = subprocess.Popen(
            all_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in process.stdout or []:
            print(line, end="")
            log_file.write(line)
            log_file.flush()

        process.wait()
        exit_code = process.returncode

        end_time = datetime.now()
        duration = end_time - start_time

        # Footer
        log_footer = f"""
{"=" * 60}
Finished: {end_time.isoformat()}
Duration: {duration}
Exit code: {exit_code}
{"=" * 60}
"""
        log_file.write(log_footer)

    # Rich footer panel
    console.print()
    if exit_code == 0:
        status = Text("PASSED", style="bold green")
        border = "green"
    else:
        status = Text("FAILED", style="bold red")
        border = "red"

    footer_text = Text()
    footer_text.append("Status: ")
    footer_text.append_text(status)
    footer_text.append(f"\nDuration: {duration}")
    footer_text.append(f"\nLog: {log_path}", style="dim")

    console.print(Panel(footer_text, border_style=border))
    sys.exit(exit_code)


def test_debug() -> None:
    """Run pytest with debug flags, capturing output to a log file.

    Flags applied:
        -n auto: Parallel execution with auto-detected workers
        --dist=loadfile: Keep tests from same file on same worker
        -x: Stop on first failure
        --ff: Run failed tests first, then remaining tests
        --durations=10: Show 10 slowest tests
        --tb=short: Shorter tracebacks

    Output saved to: test-failures.log
    """
    _run_pytest(
        title="Test Debug Run",
        log_path=Path("test-failures.log"),
        default_args=[
            "-n",
            "auto",
            "--dist=loadfile",
            "-x",
            "--ff",
            "--durations=10",
            "--tb=short",
        ],
    )


def test_all() -> None:
    """Run full test suite with parallel execution and timing.

    Flags applied:
        -n auto: Parallel execution with auto-detected workers
        --dist=loadfile: Keep tests from same file on same worker
        --durations=10: Show 10 slowest tests
        -v: Verbose output

    Output saved to: test-all.log
    """
    _run_pytest(
        title="Full Test Suite",
        log_path=Path("test-all.log"),
        default_args=["-n", "auto", "--dist=loadfile", "--durations=10", "-v"],
    )


def set_admin() -> None:
    """Set a user as admin by email.

    Usage:
        uv run set-admin user@example.com
    """
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        console.print("[red]Usage:[/] uv run set-admin <email>")
        sys.exit(1)

    email = sys.argv[1]

    if not os.environ.get("DATABASE_URL"):
        console.print("[red]Error:[/] DATABASE_URL not set")
        sys.exit(1)

    async def _set_admin() -> None:
        from sqlmodel import select

        from promptgrimoire.db.engine import get_session, init_db
        from promptgrimoire.db.models import User

        await init_db()

        async with get_session() as session:
            result = await session.exec(select(User).where(User.email == email))
            user = result.one_or_none()

            if user is None:
                console.print(f"[red]Error:[/] No user found with email '{email}'")
                console.print(
                    "[dim]User must log in at least once before being set as admin.[/]"
                )
                sys.exit(1)
                return  # unreachable, but helps type checker

            if user.is_admin:
                console.print(f"[yellow]User '{email}' is already an admin.[/]")
                return

            user.is_admin = True
            session.add(user)
            await session.commit()
            console.print(f"[green]Success:[/] '{email}' is now an admin.")

    asyncio.run(_set_admin())


def _find_export_dir(user_id: str | None) -> Path:
    """Find the export directory for a user or most recent."""
    import tempfile

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
    import re

    from rich.syntax import Syntax

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


def show_export_log() -> None:
    """Show the most recent PDF export LaTeX log and/or source.

    Usage:
        uv run show-export-log [--tex | --both] [user_id]

    Options:
        --tex   Show the .tex source file instead of the log
        --both  Show error context from both log and tex files
    """
    from rich.syntax import Syntax

    # Parse arguments
    args = sys.argv[1:]
    show_tex = "--tex" in args
    show_both = "--both" in args
    positional = [a for a in args if not a.startswith("--")]
    user_id = positional[0] if positional else None

    export_dir = _find_export_dir(user_id)
    log_file = export_dir / "annotated_document.log"
    tex_file = export_dir / "annotated_document.tex"

    # Print file paths for easy access
    console.print(
        Panel(
            f"[bold]Export Directory:[/] {export_dir}\n"
            f"[bold]TeX Source:[/] {tex_file}\n"
            f"[bold]LaTeX Log:[/] {log_file}",
            title="PDF Export Debug Files",
            border_style="blue",
        )
    )

    if show_both:
        if not tex_file.exists() or not log_file.exists():
            console.print("[red]Error:[/] Missing .tex or .log file")
            sys.exit(1)
        _show_error_context(log_file, tex_file)
    elif show_tex:
        if not tex_file.exists():
            console.print(f"[red]Error:[/] TeX file not found: {tex_file}")
            sys.exit(1)
        with console.pager():
            console.print(Syntax(tex_file.read_text(), "latex", line_numbers=True))
    else:
        if not log_file.exists():
            console.print(f"[red]Error:[/] Log file not found: {log_file}")
            sys.exit(1)
        with console.pager():
            console.print(log_file.read_text())
