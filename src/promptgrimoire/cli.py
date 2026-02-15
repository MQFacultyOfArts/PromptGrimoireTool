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

    Uses Settings.dev.test_database_url (not database.url) to prevent
    accidentally truncating production or development databases.
    """
    from promptgrimoire.config import get_settings
    from promptgrimoire.db.bootstrap import ensure_database_exists

    test_database_url = get_settings().dev.test_database_url
    if not test_database_url:
        return  # No test database configured — skip

    # Auto-create the branch-specific database if it doesn't exist
    ensure_database_exists(test_database_url)

    # Override DATABASE__URL so Settings resolves to the test database
    os.environ["DATABASE__URL"] = test_database_url
    get_settings.cache_clear()

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
    # Reference tables seeded by migrations are excluded — their data
    # is part of the schema, not transient test data.
    from sqlalchemy import create_engine, text

    _REFERENCE_TABLES = frozenset({"alembic_version", "permission", "course_role"})

    sync_url = test_database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        table_query = conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
            """)
        )
        tables = [
            row[0] for row in table_query.fetchall() if row[0] not in _REFERENCE_TABLES
        ]

        if tables:
            quoted_tables = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {quoted_tables} RESTART IDENTITY CASCADE"))

    engine.dispose()


def _build_test_header(
    title: str,
    branch: str | None,
    db_name: str,
    start_time: datetime,
    command_str: str,
) -> tuple[Text, str]:
    """Build Rich Text panel content and plain-text log header for test runs.

    Returns:
        (rich_text, log_header) tuple.
    """
    header_text = Text()
    header_text.append(f"{title}\n", style="bold")
    header_text.append(f"Branch: {branch or 'detached/unknown'}\n", style="dim")
    header_text.append(f"Test DB: {db_name}\n", style="dim")
    header_text.append(f"Started: {start_time.strftime('%H:%M:%S')}\n", style="dim")
    header_text.append(f"Command: {command_str}", style="cyan")

    log_header = f"""{"=" * 60}
{title}
Branch: {branch or "detached/unknown"}
Test DB: {db_name}
Started: {start_time.isoformat()}
Command: {command_str}
{"=" * 60}

"""
    return header_text, log_header


def _run_pytest(
    title: str,
    log_path: Path,
    default_args: list[str],
) -> None:
    """Run pytest with Rich formatting and logging."""
    _pre_test_db_cleanup()

    from promptgrimoire.config import get_current_branch, get_settings

    branch = get_current_branch()
    test_db_url = get_settings().dev.test_database_url or ""
    db_name = (
        test_db_url.split("?")[0].rsplit("/", 1)[-1]
        if test_db_url
        else "not configured"
    )

    start_time = datetime.now()
    user_args = sys.argv[1:]
    all_args = ["uv", "run", "pytest", *default_args, *user_args]
    command_str = " ".join(all_args[2:])

    header_text, log_header = _build_test_header(
        title, branch, db_name, start_time, command_str
    )
    console.print(Panel(header_text, border_style="blue"))

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

    Excludes E2E tests (same as test-all) because Playwright's event loop
    contaminates xdist workers. See #121.

    Flags applied:
        --depper: Enable smart test selection based on changed files
        --depper-run-all-on-error: Fall back to all tests if analysis fails
        -m "not e2e": Exclude Playwright E2E tests by marker
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
            "-m",
            "not e2e",
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


# Near-duplicate of _SERVER_SCRIPT in tests/conftest.py — keep in sync.
_E2E_SERVER_SCRIPT = """\
import os
import sys
from pathlib import Path

for key in list(os.environ.keys()):
    if 'PYTEST' in key or 'NICEGUI' in key:
        del os.environ[key]

os.environ['AUTH_MOCK'] = 'true'
os.environ['STORAGE_SECRET'] = 'test-secret-for-e2e'
os.environ.setdefault('STYTCH_SSO_CONNECTION_ID', 'test-sso-connection-id')
os.environ.setdefault('STYTCH_PUBLIC_TOKEN', 'test-public-token')

port = int(sys.argv[1])

from nicegui import app, ui
import promptgrimoire.pages  # noqa: F401

import promptgrimoire
_static_dir = Path(promptgrimoire.__file__).parent / "static"
app.add_static_files("/static", str(_static_dir))

ui.run(port=port, reload=False, show=False, storage_secret='test-secret-for-e2e')
"""


def _start_e2e_server(port: int) -> subprocess.Popen[bytes]:
    """Start a NiceGUI server subprocess for E2E tests.

    Returns the Popen handle. Blocks until the server accepts connections
    or fails with ``sys.exit(1)`` on timeout/crash.
    """
    import socket
    import time

    clean_env = {
        k: v for k, v in os.environ.items() if "PYTEST" not in k and "NICEGUI" not in k
    }

    console.print(f"[blue]Starting NiceGUI server on port {port}...[/]")
    process = subprocess.Popen(
        [sys.executable, "-c", _E2E_SERVER_SCRIPT, str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_env,
    )

    max_wait = 15
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if process.poll() is not None:
            out = process.stdout.read() if process.stdout else b""
            err = process.stderr.read() if process.stderr else b""
            console.print(
                f"[red]Server died (exit {process.returncode}):[/]\n"
                f"{err.decode()}\n{out.decode()}"
            )
            sys.exit(1)
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                return process
        except OSError:
            time.sleep(0.1)

    process.terminate()
    console.print(f"[red]Server failed to start within {max_wait}s[/]")
    sys.exit(1)


def _stop_e2e_server(process: subprocess.Popen[bytes]) -> None:
    """Terminate a server subprocess gracefully."""
    console.print("[dim]Stopping server...[/]")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def test_e2e() -> None:
    """Start a NiceGUI server and run Playwright E2E tests against it.

    Manages the full E2E lifecycle:
    1. Run Alembic migrations and truncate test database
    2. Start NiceGUI server on a random port (single instance)
    3. Run ``pytest -m e2e`` with xdist -- all workers share one server
    4. Shut down the server when tests complete

    The server URL is passed via ``E2E_BASE_URL`` env var. The
    ``app_server`` fixture checks this and yields it directly instead
    of starting its own server per xdist worker.

    Extra arguments forwarded to pytest (e.g. ``uv run test-e2e -k browser``).

    Output saved to: test-e2e.log
    """
    import socket

    # Eagerly load settings so .env is read before subprocess spawning.
    from promptgrimoire.config import get_settings

    get_settings()

    _pre_test_db_cleanup()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    url = f"http://localhost:{port}"
    server_process = _start_e2e_server(port)
    console.print(f"[green]Server ready at {url}[/]")

    # All xdist workers inherit this and skip starting their own server
    os.environ["E2E_BASE_URL"] = url

    try:
        _run_pytest(
            title=f"E2E Test Suite (Playwright) — server {url}",
            log_path=Path("test-e2e.log"),
            default_args=[
                "-m",
                "e2e",
                "-n",
                "auto",
                "--dist=loadfile",
                "--durations=10",
                "--tb=short",
                "-v",
            ],
        )
    finally:
        _stop_e2e_server(server_process)


def set_admin() -> None:
    """Set a user as admin by email.

    Usage:
        uv run set-admin user@example.com
    """
    from promptgrimoire.config import get_settings

    if len(sys.argv) < 2:
        console.print("[red]Usage:[/] uv run set-admin <email>")
        sys.exit(1)

    email = sys.argv[1]

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
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


async def _seed_enrolment_and_weeks(course) -> None:
    """Enrol mock users and create weeks with activities."""
    from promptgrimoire.db.activities import create_activity
    from promptgrimoire.db.courses import (
        DuplicateEnrollmentError,
        enroll_user,
        update_course,
    )
    from promptgrimoire.db.users import find_or_create_user
    from promptgrimoire.db.weeks import create_week

    # Seed all mock users and enrol them
    mock_users = [
        ("instructor@uni.edu", "Test Instructor", "coordinator"),
        ("admin@example.com", "Admin User", "coordinator"),
        ("student@uni.edu", "Test Student", "student"),
        ("test@example.com", "Test User", "student"),
    ]

    from promptgrimoire.db.engine import get_session

    for email, name, role in mock_users:
        u, created = await find_or_create_user(email=email, display_name=name)
        if email == "admin@example.com" and not u.is_admin:
            u.is_admin = True
            async with get_session() as session:
                session.add(u)
                await session.commit()
        status = "[green]Created" if created else "[yellow]Exists"
        console.print(f"{status}:[/] {email}")

        try:
            await enroll_user(course_id=course.id, user_id=u.id, role=role)
            console.print(f"  [green]Enrolled:[/] {email} as {role}")
        except DuplicateEnrollmentError:
            console.print(f"  [yellow]Already enrolled:[/] {email}")

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
    # Publish week 1; week 2 stays draft (is_published defaults to False)
    week1.is_published = True
    async with get_session() as session:
        session.add(week1)
        await session.commit()
    week2 = await create_week(
        course_id=course.id, week_number=2, title="Client Interviews"
    )
    console.print(f"[green]Created weeks:[/] 1, 2 (ids={week1.id}, {week2.id})")

    desc = "Read the interview transcript and annotate key issues."
    activity = await create_activity(
        week_id=week1.id,
        title="Annotate Becky Bennett Interview",
        description=desc,
        copy_protection=True,
    )
    console.print(f"[green]Created activity:[/] {activity.title} (id={activity.id})")

    await update_course(course.id, default_copy_protection=True)
    console.print("[green]Enabled:[/] default copy protection on course")


def seed_data() -> None:
    """Seed the database with test data for development.

    Creates an instructor user, a course with two weeks, and an activity.
    Idempotent: safe to run multiple times. Existing data is reused.

    Usage:
        uv run seed-data
    """
    from promptgrimoire.config import get_settings

    if not get_settings().database.url:
        console.print("[red]Error:[/] DATABASE__URL not set")
        sys.exit(1)

    async def _seed() -> None:
        from promptgrimoire.db.engine import init_db

        await init_db()

        _user, course = await _seed_user_and_course()
        await _seed_enrolment_and_weeks(course)

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
