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


def _pre_test_db_cleanup() -> None:
    """Run Alembic migrations and truncate all tables before tests.

    This runs once in the CLI process before pytest is spawned,
    avoiding deadlocks when xdist workers try to truncate simultaneously.

    Uses TEST_DATABASE_URL (not DATABASE_URL) to prevent accidentally
    truncating production or development databases.
    """
    from dotenv import load_dotenv

    load_dotenv()

    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        return  # No test database configured — skip

    # Override DATABASE_URL so Alembic migrations target the test database
    os.environ["DATABASE_URL"] = test_database_url

    # Run Alembic migrations
    project_root = Path(__file__).parent.parent.parent
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        console.print(f"[red]Alembic migration failed:[/]\n{result.stderr}")
        sys.exit(1)

    # Truncate all tables (sync connection, single process — no race)
    from sqlalchemy import create_engine, text

    sync_url = test_database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        table_query = conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename != 'alembic_version'
            """)
        )
        tables = [row[0] for row in table_query.fetchall()]

        if tables:
            quoted_tables = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))

    engine.dispose()


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
) -> None:
    """Run pytest with Rich formatting and logging."""
    _pre_test_db_cleanup()

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
    """Run pytest on tests affected by recent changes, stopping on first failure.

    Uses pytest-depper for smart test selection based on code dependencies.
    Only tests that depend on changed files (vs main branch) will run.

    Flags applied:
        --depper: Enable smart test selection based on changed files
        --depper-run-all-on-error: Fall back to all tests if analysis fails
        -n auto: Parallel execution with auto-detected workers
        --dist=worksteal: Workers steal tests from others for better load balancing
        -x: Stop on first failure
        --ff: Run failed tests first, then remaining tests
        --durations=10: Show 10 slowest tests
        --tb=short: Shorter tracebacks

    Output saved to: test-failures.log
    """
    _run_pytest(
        title="Test Debug Run (changed files only)",
        log_path=Path("test-failures.log"),
        default_args=[
            "--depper",
            "--depper-run-all-on-error",
            "-n",
            "auto",
            "--dist=worksteal",
            "-x",
            "--ff",
            "--durations=10",
            "--tb=short",
        ],
    )


def test_all() -> None:
    """Run unit and integration tests under xdist parallel execution.

    Excludes E2E tests because Playwright's event loop contaminates xdist
    workers, causing 'Runner.run() cannot be called from a running event loop'
    in async integration tests. See #121.

    E2E tests must run separately (they need a live app server anyway).

    Flags applied:
        -m "not e2e": Exclude Playwright E2E tests by marker
        -n auto: Parallel execution with auto-detected workers
        --dist=worksteal: Workers steal tests from others for better load balancing
        --durations=10: Show 10 slowest tests
        -v: Verbose output

    Output saved to: test-all.log
    """
    _run_pytest(
        title="Full Test Suite (unit + integration, excludes E2E)",
        log_path=Path("test-all.log"),
        default_args=[
            "-m",
            "not e2e",
            "-n",
            "auto",
            "--dist=worksteal",
            "--durations=10",
            "-v",
        ],
    )


def test_all_fixtures() -> None:
    """Run full test corpus including BLNS and slow tests.

    Runs pytest without marker filtering, enabling all tests
    including those marked with @pytest.mark.blns and @pytest.mark.slow.

    Flags applied:
        -m "": Empty marker filter = run all tests
        -v: Verbose output
        --tb=short: Shorter tracebacks

    Output saved to: test-all-fixtures.log
    """
    _run_pytest(
        title="Full Fixture Corpus (including BLNS/slow)",
        log_path=Path("test-all-fixtures.log"),
        default_args=["-m", "", "-v", "--tb=short"],
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


async def _seed_user_and_course() -> tuple:
    """Create instructor user and course. Returns (user, course)."""
    from sqlmodel import select

    from promptgrimoire.db.courses import create_course
    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Course
    from promptgrimoire.db.users import find_or_create_user

    user, user_created = await find_or_create_user(
        email="instructor@uni.edu",
        display_name="Test Instructor",
    )
    status = "[green]Created" if user_created else "[yellow]Exists"
    console.print(f"{status}:[/] instructor@uni.edu (id={user.id})")

    # Check for existing course first (code is not unique — same
    # code may appear in different semesters)
    async with get_session() as session:
        result = await session.exec(
            select(Course)
            .where(Course.code == "LAWS1100")
            .where(Course.semester == "2026-S1")
        )
        course = result.first()

    if course:
        console.print(f"[yellow]Course exists:[/] LAWS1100 (id={course.id})")
    else:
        course = await create_course(code="LAWS1100", name="Torts", semester="2026-S1")
        console.print(f"[green]Created course:[/] LAWS1100 (id={course.id})")

    return user, course


async def _seed_enrolment_and_weeks(course, user) -> None:
    """Enrol user and create weeks with activities."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import DuplicateEnrollmentError, enroll_user
    from promptgrimoire.db.models import CourseRole
    from promptgrimoire.db.weeks import create_week

    try:
        await enroll_user(
            course_id=course.id,
            user_id=user.id,
            role=CourseRole.coordinator,
        )
        console.print("[green]Enrolled:[/] instructor@uni.edu as coordinator")
    except DuplicateEnrollmentError:
        console.print("[yellow]Already enrolled:[/] instructor@uni.edu")

    from sqlmodel import select

    from promptgrimoire.db.engine import get_session
    from promptgrimoire.db.models import Week

    async with get_session() as session:
        result = await session.exec(select(Week).where(Week.course_id == course.id))
        existing_weeks = list(result.all())

    if existing_weeks:
        console.print(f"[yellow]Weeks exist:[/] {len(existing_weeks)} in course")
        return

    week1 = await create_week(course_id=course.id, week_number=1, title="Introduction")
    week2 = await create_week(
        course_id=course.id, week_number=2, title="Client Interviews"
    )
    console.print(f"[green]Created weeks:[/] 1, 2 (ids={week1.id}, {week2.id})")

    desc = "Read the interview transcript and annotate key issues."
    activity = await create_activity(
        week_id=week1.id,
        title="Annotate Becky Bennett Interview",
        description=desc,
    )
    console.print(f"[green]Created activity:[/] {activity.title} (id={activity.id})")


def seed_data() -> None:
    """Seed the database with test data for development.

    Creates an instructor user, a course with two weeks, and an activity.
    Idempotent: safe to run multiple times. Existing data is reused.

    Usage:
        uv run seed-data
    """
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DATABASE_URL"):
        console.print("[red]Error:[/] DATABASE_URL not set")
        sys.exit(1)

    async def _seed() -> None:
        from promptgrimoire.db.engine import init_db

        await init_db()

        user, course = await _seed_user_and_course()
        await _seed_enrolment_and_weeks(course, user)

        console.print()
        console.print(
            Panel(
                f"[bold]Login:[/] http://localhost:8080/login\n"
                f"[bold]Email:[/] instructor@uni.edu\n"
                f"[bold]Course:[/] http://localhost:8080/courses/{course.id}",
                title="Seed Data Ready",
            )
        )

    asyncio.run(_seed())


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
