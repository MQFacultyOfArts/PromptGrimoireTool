"""Cross-module infrastructure shared between testing and e2e modules."""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text

if TYPE_CHECKING:
    from datetime import datetime

console = Console()

# ---------------------------------------------------------------------------
# Pytest output parsing regexes (used by testing.py and e2e.py)
# ---------------------------------------------------------------------------
_COLLECTED_RE = re.compile(r"collected (\d+) items?(?:\s*/\s*(\d+) deselected)?")
_XDIST_ITEMS_RE = re.compile(r"\[(\d+) items?\]")
_RESULT_KW_RE = re.compile(r"\b(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
_PCT_RE = re.compile(r"\[\s*(\d+)%\s*\]")
_SEPARATOR_RE = re.compile(r"^={5,}")


def _prepend_filter(extra_args: list[str], filter_expr: str | None) -> list[str]:
    """Inject ``-k EXPR`` into *extra_args* when a filter is given."""
    if filter_expr:
        return ["-k", filter_expr, *extra_args]
    return extra_args


def _prepend_pytest_flags(
    extra_args: list[str],
    *,
    exit_first: bool = False,
    failed_first: bool = False,
) -> list[str]:
    """Inject ``-x`` and/or ``--ff`` into *extra_args* when requested."""
    prefix: list[str] = []
    if exit_first:
        prefix.append("-x")
    if failed_first:
        prefix.append("--ff")
    if prefix:
        return [*prefix, *extra_args]
    return extra_args


def _clone_source_db_name(test_database_url: str) -> str:
    """Derive the private clone-source database name from the test DB URL.

    Appends ``_clone_source`` to the test database name so that
    ``test_db_cloning.py`` can use it as a template without killing
    other xdist workers' connections via ``pg_terminate_backend()``.
    """
    base = test_database_url.split("?", maxsplit=1)[0]
    db_name = base.rsplit("/", 1)[1]
    return f"{db_name}_clone_source"


def _build_clone_source_url(test_database_url: str, clone_source_name: str) -> str:
    """Replace the database name in *test_database_url* with *clone_source_name*."""
    base = test_database_url.split("?", maxsplit=1)[0]
    prefix = base.rsplit("/", 1)[0]
    query = ""
    if "?" in test_database_url:
        query = "?" + test_database_url.split("?", 1)[1]
    return f"{prefix}/{clone_source_name}{query}"


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
    # Signal engine module to use NullPool instead of QueuePool.
    # Inherited by all xdist workers.  Avoids asyncpg connection-state
    # leakage under parallel execution (asyncpg#784, SQLAlchemy#10226).
    os.environ["_PROMPTGRIMOIRE_USE_NULL_POOL"] = "1"
    get_settings.cache_clear()

    # Run Alembic migrations
    project_root = Path(__file__).parent.parent.parent.parent
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

    # Create a private clone-source database for test_db_cloning.py.
    # clone_database() calls pg_terminate_backend() on the source DB,
    # which would kill every other xdist worker's connection if the
    # shared test DB were used directly.  Creating the clone source here
    # (before xdist workers connect) avoids the race.
    from promptgrimoire.db.bootstrap import clone_database, drop_database

    clone_source_name = _clone_source_db_name(test_database_url)
    clone_source_url = _build_clone_source_url(test_database_url, clone_source_name)

    # Drop stale leftover from a previous crashed run
    with contextlib.suppress(Exception):
        drop_database(clone_source_url)

    clone_database(test_database_url, clone_source_name)
    os.environ["_CLONE_TEST_SOURCE_URL"] = clone_source_url


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
